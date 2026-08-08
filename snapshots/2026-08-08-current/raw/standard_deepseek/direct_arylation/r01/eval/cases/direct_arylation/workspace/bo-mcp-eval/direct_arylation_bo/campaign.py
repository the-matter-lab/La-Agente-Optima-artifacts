# direct_arylation_bo/campaign.py
"""BO-MCP campaign orchestrator for direct arylation yield optimisation.

Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from direct_arylation_bo.evaluator import OracleEvaluator
from direct_arylation_bo.intake import build_intake

# ── tagged output helpers ───────────────────────────────────────────

_TAGS = {
    "event": "[EVENT]",
    "alert": "[ALERT]",
    "result": "[RESULT]",
    "heartbeat": "[HEARTBEAT]",
}


def _emit(tag: str, msg: str) -> None:
    print(f"{_TAGS[tag]} {msg}", flush=True)


# ── campaign runner ─────────────────────────────────────────────────


def run_campaign(
    *,
    campaign_id: str | None = None,
    max_attempts: int = 60,
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    stop_file: str = "STOP",
    artifact_dir: str = "artifacts",
) -> dict[str, Any]:
    """Execute the BO-MCP campaign loop.

    Parameters
    ----------
    campaign_id:
        If given, resume/reopen an existing campaign instead of creating one.
    max_attempts:
        Hard budget of oracle evaluations for this invocation.
    poll_s:
        Seconds between next_action polls when the server says wait.
    heartbeat_s:
        Seconds between liveness heartbeats.
    stop_file:
        Path to a stop-marker file; delete it and exit cleanly when found.
    artifact_dir:
        Directory for append-only provenance files (results JSONL, etc.).

    Returns
    -------
    dict with keys: campaign_id, best_yield, best_candidate, n_attempted,
    n_successful, n_failed, attempts_log_path.
    """
    client = BoMcpClient.from_env()
    evaluator = OracleEvaluator()

    # ── create or resume campaign ───────────────────────────────────
    if campaign_id is None:
        intake = build_intake()
        _emit("event", "Validating campaign intake …")
        client.validate_intake(intake)
        _emit("event", "Creating campaign …")
        create_resp = client.create_campaign(
            intake, idempotency_key=client.make_idempotency_key("create")
        )
        if not create_resp.get("success"):
            raise BoMcpOperationError(
                f"Campaign creation rejected: {create_resp.get('errors')}",
                create_resp,
            )
        campaign_id = create_resp["campaign_id"]
        _emit("event", f"Created campaign {campaign_id}")
    else:
        # Resume or reopen
        status_info = client.next_action(campaign_id)
        current_status = status_info.get("status", "unknown")
        if current_status == "paused":
            _emit("event", f"Resuming paused campaign {campaign_id}")
            client.lifecycle(campaign_id, action="resume")
        elif current_status == "completed":
            _emit("event", f"Reopening completed campaign {campaign_id}")
            client.lifecycle(campaign_id, action="reopen")
        elif current_status == "running":
            _emit("event", f"Campaign {campaign_id} is already running")
        else:
            _emit("alert", f"Campaign {campaign_id} status={current_status}; attempting resume")
            client.lifecycle(campaign_id, action="resume")

    # ── artifact setup ──────────────────────────────────────────────
    artifacts = Path(artifact_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    attempts_log = artifacts / f"attempts_{campaign_id}.jsonl"

    # ── loop state ──────────────────────────────────────────────────
    n_attempted = 0
    n_successful = 0
    n_failed = 0
    best_yield: float | None = None
    best_candidate: dict[str, Any] | None = None
    last_heartbeat = time.monotonic()

    _emit("event", f"Starting BO loop — budget: {max_attempts} attempts")

    while n_attempted < max_attempts:
        # ── stop-file check ─────────────────────────────────────────
        if os.path.exists(stop_file):
            _emit("event", f"Stop file '{stop_file}' found — shutting down cleanly")
            os.remove(stop_file)
            break

        # ── heartbeat ───────────────────────────────────────────────
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _emit("heartbeat", (
                f"attempted={n_attempted}/{max_attempts} "
                f"successful={n_successful} failed={n_failed} "
                f"best_yield={best_yield}"
            ))
            last_heartbeat = now

        # ── ask server what to do ───────────────────────────────────
        try:
            decision = client.next_action(campaign_id)
        except (BoMcpClientError, BoMcpOperationError) as exc:
            _emit("alert", f"next_action failed: {exc}; retrying in {poll_s}s")
            time.sleep(poll_s)
            continue

        action = decision.get("action")
        reason = decision.get("reason", "")
        n_results = decision.get("n_results", 0)

        if action != "bo_generate_suggestions":
            _emit("event", (
                f"Server says stop: action={action} reason={reason} "
                f"n_results={n_results}"
            ))
            break

        # ── generate suggestion ─────────────────────────────────────
        try:
            gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
        except (BoMcpClientError, BoMcpOperationError) as exc:
            _emit("alert", f"generate_suggestions failed: {exc}; retrying in {poll_s}s")
            time.sleep(poll_s)
            continue

        if not gen_resp.get("success"):
            _emit("alert", f"Generation rejected: {gen_resp.get('errors')}")
            break

        suggestions = gen_resp.get("suggestions") or []
        if not suggestions:
            _emit("alert", "No suggestions returned; polling …")
            time.sleep(poll_s)
            continue

        suggestion = suggestions[0]
        suggestion_id = suggestion["suggestion_id"]
        candidate = dict(suggestion["parameter_values"])

        # ── evaluate ────────────────────────────────────────────────
        n_attempted += 1
        _emit("event", (
            f"Evaluating candidate {n_attempted}/{max_attempts}: "
            f"base={candidate['base']} ligand={candidate['ligand']} "
            f"solvent={candidate['solvent']} "
            f"conc={candidate['concentration']} "
            f"T={candidate['temperature_c']}°C"
        ))

        eval_result = evaluator.evaluate(candidate)

        # ── record attempt ──────────────────────────────────────────
        attempt_record = {
            "attempt": n_attempted,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suggestion_id": suggestion_id,
            "candidate": candidate,
            "success": eval_result.success,
            "yield": eval_result.yield_value,
            "error": eval_result.error,
        }
        with open(attempts_log, "a") as fh:
            fh.write(json.dumps(attempt_record) + "\n")

        if eval_result.success:
            n_successful += 1
            yld = eval_result.yield_value
            _emit("result", (
                f"Attempt {n_attempted}: yield={yld:.2f}% "
                f"base={candidate['base']} ligand={candidate['ligand']} "
                f"solvent={candidate['solvent']} "
                f"conc={candidate['concentration']} T={candidate['temperature_c']}°C"
            ))

            if best_yield is None or yld > best_yield:
                best_yield = yld
                best_candidate = dict(candidate)
                _emit("event", f"New best: yield={best_yield:.2f}%")

            # Submit result
            result_payload = {
                "objective_values": {"yield": yld},
                "parameter_values": candidate,
                "suggestion_id": suggestion_id,
            }
            try:
                submit_resp = client.submit_results(
                    campaign_id,
                    results=[result_payload],
                    idempotency_key=client.make_idempotency_key(
                        "submit", suggestion_id
                    ),
                )
                if not submit_resp.get("success"):
                    _emit("alert", (
                        f"Result submission rejected: {submit_resp.get('errors')} "
                        f"field_errors={submit_resp.get('field_errors')}"
                    ))
            except (BoMcpClientError, BoMcpOperationError) as exc:
                _emit("alert", f"submit_results failed: {exc}")
        else:
            n_failed += 1
            _emit("alert", (
                f"Attempt {n_attempted} FAILED: {eval_result.error} "
                f"candidate={candidate}"
            ))
            # Reject the suggestion so BO doesn't re-recommend it
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
            except (BoMcpClientError, BoMcpOperationError):
                pass

    # ── shutdown ────────────────────────────────────────────────────
    _emit("event", "Loop finished — fetching final diagnostics …")

    # Pause (not terminate) so the campaign stays resumable
    try:
        status_info = client.next_action(campaign_id)
        if status_info.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            _emit("event", "Campaign paused")
    except (BoMcpClientError, BoMcpOperationError) as exc:
        _emit("alert", f"Pause failed (campaign may already be stopped): {exc}")

    # ── final report ────────────────────────────────────────────────
    _emit("event", "=" * 60)
    _emit("event", "FINAL REPORT")
    _emit("event", f"  Campaign ID:    {campaign_id}")
    _emit("event", f"  Attempted:      {n_attempted}")
    _emit("event", f"  Successful:     {n_successful}")
    _emit("event", f"  Failed:         {n_failed}")
    if best_yield is not None:
        _emit("event", f"  Best yield:     {best_yield:.2f}%")
        _emit("event", f"  Best candidate: {json.dumps(best_candidate)}")
    _emit("event", f"  Attempts log:   {attempts_log}")
    _emit("event", "=" * 60)

    return {
        "campaign_id": campaign_id,
        "best_yield": best_yield,
        "best_candidate": best_candidate,
        "n_attempted": n_attempted,
        "n_successful": n_successful,
        "n_failed": n_failed,
        "attempts_log_path": str(attempts_log),
    }