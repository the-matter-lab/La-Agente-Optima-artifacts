"""Campaign orchestrator — BO-MCP loop for the 6D Ackley benchmark."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any

# Ensure /app is on sys.path for domains imports
_APP_DIR = os.environ.get("APP_DIR", "/app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from ackley6d.campaign_intake import build_intake
from ackley6d.candidate_evaluator import evaluate
from ackley6d.objective_reporting import (
    append_artifact,
    build_result_row,
    compute_summary,
    write_results_csv,
)
from ackley6d.search_space import PARAM_NAMES

# Tagged-line prefixes for the monitor
TAG_EVENT = "[EVENT]"
TAG_ALERT = "[ALERT]"
TAG_RESULT = "[RESULT]"
TAG_HEARTBEAT = "[HEARTBEAT]"


def _print(tag: str, msg: str) -> None:
    print(f"{tag} {msg}", flush=True)


def run_campaign(
    *,
    client: BoMcpClient,
    campaign_id: str | None = None,
    max_evaluations: int = 60,
    poll_s: float = 180,
    heartbeat_s: float = 1800,
    stop_file: str = "STOP",
    artifact_dir: str = "artifacts",
    random_seed: int = 42,
) -> str:
    """Execute the BO-MCP campaign loop. Returns the campaign_id."""

    os.makedirs(artifact_dir, exist_ok=True)
    artifact_path = os.path.join(artifact_dir, "evaluations.jsonl")
    csv_path = os.path.join(artifact_dir, "evaluations.csv")

    # ── Create or reuse campaign ──────────────────────────────────────
    if campaign_id is None:
        intake = build_intake(random_seed=random_seed)
        _print(TAG_EVENT, "Creating campaign …")
        idem_key = BoMcpClient.make_idempotency_key("create", uuid.uuid4().hex[:8])
        resp = client.create_campaign(intake, idempotency_key=idem_key)
        campaign_id = resp["campaign_id"]
        _print(TAG_EVENT, f"Campaign created: {campaign_id}")
    else:
        # Resume: ensure campaign is running
        info = client.next_action(campaign_id)
        status = info.get("status", "unknown")
        _print(TAG_EVENT, f"Resuming campaign {campaign_id} (status={status})")
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            _print(TAG_EVENT, "Campaign resumed")
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _print(TAG_EVENT, "Campaign reopened")

    # Expose campaign_id to caller
    _print(TAG_EVENT, f"BO_MCP_CAMPAIGN_ID={campaign_id}")

    # ── Main loop ─────────────────────────────────────────────────────
    eval_index = 0
    last_heartbeat = time.monotonic()

    while eval_index < max_evaluations:
        # Stop-file check
        if os.path.exists(stop_file):
            _print(TAG_EVENT, f"Stop file detected — pausing after {eval_index} evaluations")
            try:
                os.remove(stop_file)
            except OSError:
                pass
            # Pause only if still running
            info = client.next_action(campaign_id)
            if info.get("status") == "running":
                client.lifecycle(campaign_id, action="pause")
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _print(TAG_HEARTBEAT, f"alive eval_index={eval_index}/{max_evaluations}")
            last_heartbeat = now

        # Ask server what to do next
        try:
            decision = client.next_action(campaign_id)
        except Exception as exc:
            _print(TAG_ALERT, f"next_action failed: {exc}")
            time.sleep(5)
            continue

        action = decision.get("action")
        if action != "bo_generate_suggestions":
            _print(TAG_EVENT, f"Server recommends stop: action={action} reason={decision.get('reason')}")
            break

        # Generate suggestions
        try:
            sug_resp = client.generate_suggestions(campaign_id, batch_size=1)
        except BoMcpOperationError as exc:
            _print(TAG_ALERT, f"Suggestion generation rejected: {exc}")
            break
        except Exception as exc:
            _print(TAG_ALERT, f"Suggestion generation error: {exc}")
            time.sleep(5)
            continue

        suggestions = sug_resp.get("suggestions", [])
        if not suggestions:
            _print(TAG_EVENT, "No suggestions returned — stopping")
            break

        for suggestion in suggestions:
            if eval_index >= max_evaluations:
                break

            eval_index += 1
            sid = suggestion["suggestion_id"]
            pvals = suggestion["parameter_values"]

            # Evaluate
            try:
                result = evaluate(pvals)
                status = "success"
                failure_reason = None
            except Exception as exc:
                result = None
                status = "failed"
                failure_reason = str(exc)
                _print(TAG_ALERT, f"Evaluation {eval_index} failed: {exc}")

            submit_row, artifact_row = build_result_row(
                evaluation_index=eval_index,
                suggestion_id=sid,
                parameter_values=pvals,
                evaluator_output=result,
                status=status,
                failure_reason=failure_reason,
            )
            append_artifact(artifact_path, artifact_row)

            # Submit result to BO-MCP
            idem_key = BoMcpClient.make_idempotency_key("result", str(eval_index))
            try:
                client.submit_results(
                    campaign_id,
                    results=[submit_row],
                    idempotency_key=idem_key,
                )
            except BoMcpOperationError as exc:
                # Duplicate? Try with force
                if "duplicate" in str(exc).lower() or "E004" in str(exc):
                    _print(TAG_ALERT, f"Duplicate at eval {eval_index} — retrying with force")
                    idem_key2 = BoMcpClient.make_idempotency_key("result-force", str(eval_index))
                    try:
                        client.submit_results(
                            campaign_id,
                            results=[submit_row],
                            idempotency_key=idem_key2,
                            force=True,
                        )
                    except Exception as exc2:
                        _print(TAG_ALERT, f"Force-submit also failed: {exc2}")
                else:
                    _print(TAG_ALERT, f"Result submission failed: {exc}")

            _print(TAG_RESULT, (
                f"eval={eval_index}/{max_evaluations} "
                f"status={status} "
                f"surface_response={artifact_row['objective_values']['surface_response']:.6f} "
                f"raw_response={artifact_row.get('raw_response', 'N/A')}"
            ))

    # ── End-of-invocation ─────────────────────────────────────────────
    _print(TAG_EVENT, f"Evaluation budget exhausted or loop ended at {eval_index} evaluations")

    # Pause campaign (not terminate — allows continuation)
    try:
        info = client.next_action(campaign_id)
        if info.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            _print(TAG_EVENT, "Campaign paused")
    except Exception as exc:
        _print(TAG_ALERT, f"Failed to pause campaign: {exc}")

    # Write CSV and summary
    n_csv = write_results_csv(artifact_path, csv_path)
    _print(TAG_EVENT, f"Wrote {n_csv} rows to {csv_path}")

    # Load all rows for summary
    rows = []
    if os.path.exists(artifact_path):
        with open(artifact_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    summary = compute_summary(rows)
    summary_path = os.path.join(artifact_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    _print(TAG_EVENT, f"Summary: {json.dumps(summary, default=str)}")
    _print(TAG_EVENT, f"BO_MCP_CAMPAIGN_ID={campaign_id}")

    return campaign_id
