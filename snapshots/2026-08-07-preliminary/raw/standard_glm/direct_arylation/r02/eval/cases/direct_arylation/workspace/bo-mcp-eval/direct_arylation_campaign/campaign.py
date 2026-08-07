"""Campaign orchestration — the core BO loop.

This module owns the iteration logic: generate suggestions, evaluate
candidates, submit results, and respect the CLI budget.  It delegates
to the other package modules for search-space, intake, evaluation,
and reporting concerns.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from direct_arylation_campaign.evaluation import evaluate_candidate
from direct_arylation_campaign.intake import build_intake
from direct_arylation_campaign.reporting import print_summary, record_attempt
from direct_arylation_campaign.search_space import MARKER


def _tag(tag: str, msg: str) -> None:
    """Print a tagged, unbuffered line for the monitor."""
    print(f"[{tag}] {msg}", flush=True)


def run_campaign(
    *,
    client: BoMcpClient,
    campaign_id: str | None,
    max_attempts: int = 60,
    artifact_dir: str,
    stop_file: str = "STOP",
    poll_s: float = 5.0,
    heartbeat_s: float = 1800.0,
) -> str:
    """Execute the BO loop and return the campaign_id.

    Parameters
    ----------
    client : BoMcpClient
        Authenticated BO-MCP REST client.
    campaign_id : str | None
        Existing campaign to resume, or ``None`` to create a new one.
    max_attempts : int
        Per-invocation budget for attempted objective evaluations.
    artifact_dir : str
        Directory for the JSONL evaluation log.
    stop_file : str
        Path checked at the top of each iteration; if present, pause.
    poll_s : float
        Seconds to sleep between iterations (rate-limit padding).
    heartbeat_s : float
        Seconds between [HEARTBEAT] lines.
    """
    # ── Create or resume ──────────────────────────────────────────
    if campaign_id is None:
        intake = build_intake(campaign_label="run")
        _tag("EVENT", f"Creating campaign: {intake['name']}")
        idem_key = f"create-{uuid.uuid4().hex[:12]}"
        try:
            resp = client.create_campaign(intake, idempotency_key=idem_key)
            campaign_id = resp.get("campaign_id")
        except BoMcpOperationError as exc:
            # success=false from the server
            _tag("ALERT", f"Campaign creation rejected: {exc}")
            raise
        if not campaign_id:
            _tag("ALERT", f"No campaign_id in response: {resp}")
            raise RuntimeError(f"No campaign_id returned: {resp}")
        _tag("EVENT", f"Campaign created: {campaign_id}")
    else:
        _tag("EVENT", f"Resuming campaign: {campaign_id}")
        # If the campaign is paused or completed, resume/reopen it.
        try:
            status_info = client.next_action(campaign_id)
        except (BoMcpClientError, BoMcpOperationError):
            _tag("ALERT", f"Cannot query campaign {campaign_id}")
            raise
        status = status_info.get("status", "")
        if status == "paused":
            _tag("EVENT", "Campaign is paused — resuming")
            client.lifecycle(campaign_id, action="resume")
        elif status == "completed":
            _tag("EVENT", "Campaign is completed — reopening")
            client.lifecycle(campaign_id, action="reopen")

    # ── Main loop ─────────────────────────────────────────────────
    attempt_count = 0
    last_heartbeat = time.monotonic()

    while attempt_count < max_attempts:
        # Stop-file check (before generating a suggestion)
        if os.path.exists(stop_file):
            _tag("EVENT", f"Stop file detected ({stop_file}) — pausing campaign")
            try:
                os.remove(stop_file)
            except OSError:
                pass
            try:
                client.lifecycle(campaign_id, action="pause")
            except Exception:
                pass
            _tag("EVENT", "Campaign paused. Resume by re-running with --campaign-id")
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _tag("HEARTBEAT", f"attempt {attempt_count}/{max_attempts}, campaign {campaign_id}")
            last_heartbeat = now

        # Ask the server what to do next
        try:
            decision = client.next_action(campaign_id)
        except (BoMcpClientError, BoMcpOperationError) as exc:
            _tag("ALERT", f"next_action failed: {exc}")
            time.sleep(poll_s)
            continue

        action = decision.get("action")
        if action not in ("bo_generate_suggestions", "bo_submit_results"):
            reason = decision.get("reason", "unknown")
            _tag("EVENT", f"Server recommends stop: action={action}, reason={reason}")
            break

        # Get a suggestion: either query pending ones or generate new ones.
        suggestion = None
        if action == "bo_submit_results":
            # There are pending suggestions — pick one up.
            _tag("EVENT", "Pending suggestions found — evaluating one")
            try:
                pending = client.query_suggestions(
                    campaign_id, status_filter="pending"
                )
            except (BoMcpClientError, BoMcpOperationError) as exc:
                _tag("ALERT", f"Query pending suggestions failed: {exc}")
                time.sleep(poll_s)
                continue
            if pending:
                suggestion = pending[0]

        if suggestion is None:
            # Generate a new suggestion
            _tag("EVENT", f"Generating suggestion (attempt {attempt_count + 1}/{max_attempts})")
            try:
                gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
            except (BoMcpClientError, BoMcpOperationError) as exc:
                _tag("ALERT", f"Suggestion generation failed: {exc}")
                time.sleep(poll_s)
                continue

            suggestions = gen_resp.get("suggestions", [])
            if not suggestions:
                errors = gen_resp.get("errors", [])
                _tag("ALERT", f"No suggestions returned: {errors}")
                time.sleep(poll_s)
                continue
            suggestion = suggestions[0]

        suggestion_id = suggestion.get("suggestion_id", "")
        param_vals = suggestion.get("parameter_values", {})

        # Evaluate the candidate
        attempt_count += 1
        _tag("EVENT", f"Evaluating attempt {attempt_count}: {param_vals}")
        eval_result = evaluate_candidate(param_vals)

        # Record the attempt locally
        record_attempt(
            artifact_dir,
            attempt_index=attempt_count,
            parameter_values=eval_result["parameter_values"],
            status=eval_result["status"],
            objective_values=eval_result.get("objective_values"),
            error=eval_result.get("error"),
            suggestion_id=suggestion_id,
        )

        if eval_result["status"] == "success":
            yield_val = eval_result["objective_values"]["yield"]
            _tag("RESULT", f"Attempt {attempt_count}: yield={yield_val:.2f}% | {param_vals}")

            # Submit result to BO-MCP
            result_payload = {
                "suggestion_id": suggestion_id,
                "parameter_values": eval_result["parameter_values"],
                "objective_values": eval_result["objective_values"],
            }
            idem_key = BoMcpClient.make_idempotency_key(
                "result", campaign_id, str(attempt_count)
            )
            try:
                client.submit_results(
                    campaign_id,
                    results=[result_payload],
                    idempotency_key=idem_key,
                )
            except (BoMcpClientError, BoMcpOperationError) as exc:
                _tag("ALERT", f"Result submission failed: {exc}")
        else:
            _tag("ALERT", f"Attempt {attempt_count} FAILED: {eval_result.get('error', 'unknown')} | {param_vals}")

            # Mark the suggestion as failed so BO-MCP knows
            try:
                client.update_suggestion_status(suggestion_id, status="failed")
            except (BoMcpClientError, BoMcpOperationError) as exc:
                _tag("ALERT", f"Suggestion status update failed: {exc}")

        time.sleep(poll_s)

    # ── End-of-invocation ─────────────────────────────────────────
    _tag("EVENT", f"Invocation complete: {attempt_count} attempts made")

    # Print summary
    print_summary(artifact_dir)

    # Fetch diagnostics (generous timeout for a grown campaign)
    _tag("EVENT", "Fetching campaign diagnostics")
    try:
        diag = client.get_diagnostics(campaign_id, timeout_s=300.0)
        diag_path = os.path.join(artifact_dir, "diagnostics.json")
        import json
        with open(diag_path, "w") as f:
            json.dump(diag, f, indent=2, default=str)
        _tag("EVENT", f"Diagnostics saved to {diag_path}")
    except Exception as exc:
        _tag("ALERT", f"Diagnostics fetch failed: {exc}")

    # Pause the campaign (not terminate — allows resume)
    try:
        client.lifecycle(campaign_id, action="pause")
        _tag("EVENT", "Campaign paused for potential resume")
    except Exception as exc:
        _tag("ALERT", f"Pause failed: {exc}")

    # Print the campaign ID for the main agent
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)

    return campaign_id
