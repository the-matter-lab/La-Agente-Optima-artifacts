"""Campaign orchestration — the core BO loop.

This module owns the iteration logic: generate suggestions, evaluate
candidates, submit results, and respect the invocation budget.  It
delegates to the other package modules for search-space, intake,
evaluation, and reporting concerns.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from direct_arylation_bo.campaign_intake import OWNERSHIP_MARKER, build_intake
from direct_arylation_bo.evaluator import evaluate_candidate
from direct_arylation_bo.reporting import (
    append_artifact,
    make_attempt_record,
    write_final_report,
)


def _print(tag: str, msg: str) -> None:
    """Unbuffered tagged print for monitor filtering."""
    line = f"[{tag}] {msg}"
    print(line, flush=True)


def run_campaign(
    *,
    client: BoMcpClient,
    campaign_id: str | None = None,
    budget: int = 60,
    artifact_dir: Path,
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    stop_file: Path | None = None,
) -> str:
    """Execute the BO loop and return the campaign_id.

    Parameters
    ----------
    client : BoMcpClient
        Authenticated BO-MCP REST client.
    campaign_id : str | None
        Existing campaign to resume.  None → create a new one.
    budget : int
        Maximum attempted evaluations for this invocation.
    artifact_dir : Path
        Directory for JSONL artifact and final report.
    poll_s, heartbeat_s : int
        Polling and heartbeat intervals (seconds).
    stop_file : Path | None
        File whose existence signals a graceful pause request.

    Returns
    -------
    str
        The campaign_id used.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "attempts.jsonl"

    # ── Create or resume ──────────────────────────────────────────────
    if campaign_id is None:
        intake = build_intake()
        idem_key = f"create-{OWNERSHIP_MARKER}-{uuid.uuid4().hex[:10]}"
        resp = client.create_campaign(intake, idempotency_key=idem_key)
        campaign_id = resp["campaign_id"]
        _print("EVENT", f"Campaign created: {campaign_id}")
    else:
        # Resume: ensure the campaign is running
        status_info = client.next_action(campaign_id)
        status = status_info.get("status", "unknown")
        _print("EVENT", f"Resuming campaign {campaign_id} (status={status})")
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            _print("EVENT", "Campaign resumed")
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _print("EVENT", "Campaign reopened")

    _print("EVENT", f"BO_MCP_CAMPAIGN_ID={campaign_id}")

    # ── Main loop ─────────────────────────────────────────────────────
    attempts: list[dict[str, Any]] = []
    attempt_count = 0
    last_heartbeat = time.monotonic()

    while attempt_count < budget:
        # Stop-file check (before generating a suggestion)
        if stop_file and stop_file.exists():
            _print("EVENT", "Stop file detected — pausing gracefully")
            stop_file.unlink(missing_ok=True)
            # Pause the campaign so it can be resumed later
            try:
                client.lifecycle(campaign_id, action="pause")
            except Exception:
                pass
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _print("HEARTBEAT", f"attempt {attempt_count}/{budget}")
            last_heartbeat = now

        # Ask the server what to do next
        try:
            decision = client.next_action(campaign_id)
        except Exception as exc:
            _print("ALERT", f"next_action failed: {exc}")
            time.sleep(5)
            continue

        action = decision.get("action")
        if action != "bo_generate_suggestions":
            reason = decision.get("reason", "unknown")
            _print("EVENT", f"Server recommends stop: action={action}, reason={reason}")
            break

        # Generate a suggestion
        try:
            gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
        except BoMcpOperationError as exc:
            # Operation-level rejection (budget exceeded, converged, etc.)
            _print("EVENT", f"Suggestion generation rejected: {exc}")
            break
        except Exception as exc:
            _print("ALERT", f"Suggestion generation error: {exc}")
            time.sleep(5)
            continue

        suggestions = gen_resp.get("suggestions", [])
        if not suggestions:
            _print("ALERT", "No suggestions returned — stopping")
            break

        suggestion = suggestions[0]
        suggestion_id = suggestion["suggestion_id"]
        params = suggestion["parameter_values"]

        attempt_count += 1
        _print("EVENT", f"Attempt {attempt_count}/{budget}: {params}")

        # Evaluate the candidate
        yield_val, success = evaluate_candidate(params)

        # Build and persist the attempt record
        record = make_attempt_record(
            attempt_index=attempt_count,
            suggestion_id=suggestion_id,
            parameter_values=params,
            yield_value=yield_val,
            success=success,
        )
        attempts.append(record)
        append_artifact(artifact_path, record)

        if success:
            _print("RESULT", f"yield={yield_val:.2f}% | {params}")
            # Submit result to BO-MCP
            result_payload = {
                "suggestion_id": suggestion_id,
                "parameter_values": params,
                "objective_values": {"yield": yield_val},
            }
            idem_key = client.make_idempotency_key("result", campaign_id, str(attempt_count))
            try:
                client.submit_results(
                    campaign_id,
                    results=[result_payload],
                    idempotency_key=idem_key,
                )
            except BoMcpOperationError as exc:
                # Duplicate? Try with force
                if "duplicate" in str(exc).lower() or "E004" in str(exc):
                    _print("ALERT", f"Duplicate result — retrying with force")
                    idem_key2 = client.make_idempotency_key("result-force", campaign_id, str(attempt_count))
                    try:
                        client.submit_results(
                            campaign_id,
                            results=[result_payload],
                            idempotency_key=idem_key2,
                            force=True,
                        )
                    except Exception as exc2:
                        _print("ALERT", f"Force-submit also failed: {exc2}")
                else:
                    _print("ALERT", f"Result submission failed: {exc}")
        else:
            _print("ALERT", f"Evaluation failed (attempt {attempt_count})")
            # Mark the suggestion as rejected so BO doesn't wait for it
            try:
                client.update_suggestion_status(suggestion_id, status="rejected")
            except Exception as exc:
                _print("ALERT", f"Could not reject suggestion: {exc}")

    # ── Final report ──────────────────────────────────────────────────
    _print("EVENT", f"Loop ended after {attempt_count} attempts")
    summary = write_final_report(
        artifact_path=artifact_path,
        campaign_id=campaign_id,
        attempts=attempts,
    )

    best_yield = summary.get("best_yield")
    best_cond = summary.get("best_conditions")
    n_ok = summary.get("successful_evaluations", 0)
    n_fail = summary.get("failed_evaluations", 0)
    _print("RESULT", f"Best yield: {best_yield}%")
    _print("RESULT", f"Best conditions: {best_cond}")
    _print("RESULT", f"Successful: {n_ok} | Failed: {n_fail} | Total attempted: {attempt_count}")
    _print("RESULT", f"BO_MCP_CAMPAIGN_ID={campaign_id}")

    # Pause the campaign at end of invocation (not terminate — resumable)
    try:
        info = client.next_action(campaign_id)
        if info.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            _print("EVENT", "Campaign paused for resumability")
    except Exception:
        pass

    return campaign_id
