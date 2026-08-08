"""Campaign orchestration for direct arylation BO-MCP optimization."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from direct_arylation_campaign.attempt_tracking import (
    append_attempt,
    count_attempts,
    get_attempt_history,
    get_attempts_path,
)
from direct_arylation_campaign.evaluator import evaluate_batch, EvaluationError
from direct_arylation_campaign.intake import build_intake, validate_intake
from direct_arylation_campaign.reporter import compute_summary, print_campaign_report, print_final_summary_line
from direct_arylation_campaign.search_space import validate_candidate


# Constants
MARKER = "akg-eval-0c360b08e6684de0b0ed04f50bde3b2c"
NONCE = "16e7e684-7bf5-4a9b-af93-fae14403be06"
MAX_ATTEMPTS = 60
DEFAULT_POLL_S = 180
DEFAULT_HEARTBEAT_S = 1800
DEFAULT_STOP_FILE = "STOP"


class CampaignState:
    """Minimal in-memory campaign state (never persisted per BO-MCP policy)."""

    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id
        self.evaluated: list[dict[str, Any]] = []  # Evaluation attempts this run
        self.submitted_suggestion_ids: set[str] = set()
        self.last_heartbeat = time.time()


def make_idempotency_key(prefix: str, *parts: str) -> str:
    """Generate an idempotency key with prefix, parts, and random suffix."""
    joined = "-".join(p.replace("/", "_") for p in parts if p)
    return f"{prefix}-{joined}-{uuid.uuid4().hex[:10]}"


def check_stop_file(stop_file: Path) -> bool:
    """Check if stop file exists; if so, delete it and return True."""
    if stop_file.exists():
        try:
            stop_file.unlink()
            return True
        except OSError:
            return True
    return False


def log_event(msg: str) -> None:
    """Log an [EVENT] line to stdout and logfire."""
    print(f"[EVENT] {msg}", flush=True)
    logfire.info("{msg}", msg=msg)


def log_alert(msg: str) -> None:
    """Log an [ALERT] line to stdout and logfire."""
    print(f"[ALERT] {msg}", flush=True)
    logfire.warning("{msg}", msg=msg)


def log_result(msg: str) -> None:
    """Log a [RESULT] line to stdout and logfire."""
    print(f"[RESULT] {msg}", flush=True)
    logfire.info("{msg}", msg=msg)


def log_heartbeat(msg: str) -> None:
    """Log a [HEARTBEAT] line to stdout and logfire."""
    print(f"[HEARTBEAT] {msg}", flush=True)
    logfire.info("{msg}", msg=msg)


def submit_results(
    client: BoMcpClient,
    campaign_id: str,
    results: list[dict[str, Any]],
    *,
    force: bool = False,
) -> list[str]:
    """
    Submit successful evaluation results to BO-MCP.

    Args:
        client: BO-MCP client
        campaign_id: Campaign ID
        results: List of evaluation result dicts (only successful ones)
        force: Whether to force submission (for replicates)

    Returns:
        List of result IDs from BO-MCP
    """
    if not results:
        return []

    # Build BO-MCP result submission payload
    bo_results = []
    for r in results:
        if r["status"] != "success" or r["yield"] is None:
            continue
        candidate = r["candidate"]
        if not validate_candidate(candidate):
            log_alert(f"Skipping invalid candidate for submission: {candidate}")
            continue

        bo_results.append({
            "parameter_values": candidate,
            "objective_values": {"yield": r["yield"]},
            "metadata": {
                "notes": f"oracle_api; elapsed_s={r.get('elapsed_s', 0.0):.3f}",
            },
        })

    if not bo_results:
        return []

    idempotency_key = make_idempotency_key("submit", campaign_id, str(len(bo_results)))
    try:
        response = client.submit_results(
            campaign_id,
            results=bo_results,
            idempotency_key=idempotency_key,
            force=force,
        )
        result_ids = response.get("result_ids", [])
        log_event(f"Submitted {len(result_ids)} results to BO-MCP")
        return result_ids
    except BoMcpOperationError as e:
        if "duplicate" in str(e.payload).lower() and not force:
            log_alert(f"Duplicate result rejected; consider force=True for replicates: {e}")
        raise
    except BoMcpClientError as e:
        log_alert(f"Failed to submit results: {e}")
        raise


def reconcile_pending_suggestions(client: BoMcpClient, campaign_id: str) -> None:
    """
    When BO-MCP returns 'bo_submit_results', reconcile pending suggestions
    against local attempt artifact and BO-MCP results.
    
    For each pending suggestion:
    - If there's a matching successful attempt in artifact, submit the result
    - Mark the suggestion as accepted so BO-MCP can continue
    - If failed attempt, mark suggestion as rejected
    """
    log_event("Reconciling pending suggestions with artifact...")
    
    # Query pending suggestions from BO-MCP
    pending_suggestions = client.query_suggestions(campaign_id, status_filter="pending")
    if not pending_suggestions:
        log_event("No pending suggestions found")
        return
    
    log_event(f"Found {len(pending_suggestions)} pending suggestion(s)")
    
    # Load attempt history from artifact
    attempts = get_attempt_history(campaign_id)
    
    # Get already submitted results to avoid duplicates
    existing_results = client.get_results(campaign_id)
    submitted_params = set()
    for r in existing_results:
        param_vals = r.get("parameter_values", {})
        # Create a hashable key from the parameters
        key = (
            param_vals.get("base"),
            param_vals.get("ligand"),
            param_vals.get("solvent"),
            param_vals.get("concentration"),
            param_vals.get("temperature_c"),
        )
        submitted_params.add(key)
    
    for suggestion in pending_suggestions:
        suggestion_id = suggestion["suggestion_id"]
        param_values = suggestion["parameter_values"]
        
        log_event(f"Processing pending suggestion {suggestion_id}: {param_values}")
        
        # Create lookup key
        key = (
            param_values.get("base"),
            param_values.get("ligand"),
            param_values.get("solvent"),
            param_values.get("concentration"),
            param_values.get("temperature_c"),
        )
        
        # Check if this candidate has an attempt in artifact
        matching_attempt = None
        for attempt in attempts:
            attempt_key = (
                attempt.get("candidate", {}).get("base"),
                attempt.get("candidate", {}).get("ligand"),
                attempt.get("candidate", {}).get("solvent"),
                attempt.get("candidate", {}).get("concentration"),
                attempt.get("candidate", {}).get("temperature_c"),
            )
            if attempt_key == key:
                matching_attempt = attempt
                break
        
        if matching_attempt:
            log_event(f"Found matching attempt for suggestion {suggestion_id}: status={matching_attempt['status']}")
            
            if matching_attempt["status"] == "success":
                # Check if already submitted to BO-MCP
                if key in submitted_params:
                    log_event(f"Result already submitted for {suggestion_id}, marking suggestion accepted")
                else:
                    # Submit the result
                    try:
                        submit_results(client, campaign_id, [matching_attempt])
                        log_event(f"Submitted missing result for {suggestion_id}")
                    except (BoMcpClientError, BoMcpOperationError) as e:
                        log_alert(f"Failed to submit result for {suggestion_id}: {e}")
                        continue
                
                # Mark suggestion as accepted
                try:
                    client.update_suggestion_status(suggestion_id, "accepted")
                    log_event(f"Marked suggestion {suggestion_id} as accepted")
                except (BoMcpClientError, BoMcpOperationError) as e:
                    log_alert(f"Failed to update suggestion {suggestion_id} status: {e}")
            else:
                # Failed attempt - mark suggestion as rejected
                try:
                    client.update_suggestion_status(suggestion_id, "rejected")
                    log_event(f"Marked suggestion {suggestion_id} as rejected (failed attempt)")
                except (BoMcpClientError, BoMcpOperationError) as e:
                    log_alert(f"Failed to update suggestion {suggestion_id} status: {e}")
        else:
            log_alert(f"No matching attempt in artifact for pending suggestion {suggestion_id}: {param_values}")
            # Could be a suggestion that was never evaluated - mark as rejected to unblock
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                log_event(f"Marked suggestion {suggestion_id} as rejected (no attempt found)")
            except (BoMcpClientError, BoMcpOperationError) as e:
                log_alert(f"Failed to update suggestion {suggestion_id} status: {e}")


def run_optimization_loop(
    client: BoMcpClient,
    campaign_id: str,
    state: CampaignState,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    poll_s: int = DEFAULT_POLL_S,
    heartbeat_s: int = DEFAULT_HEARTBEAT_S,
    stop_file: Path,
) -> None:
    """
    Run the BO optimization loop until budget exhausted or stop condition.

    The loop follows BO-MCP server authority via next_action().
    Tracks all attempts (including failures) in local artifact for budget enforcement across resumes.
    """
    log_event(f"Starting optimization loop for campaign {campaign_id}")
    log_event(f"Total attempt budget: {max_attempts}, Poll: {poll_s}s, Heartbeat: {heartbeat_s}s")

    while True:
        # Check stop file at loop start (before generating suggestions)
        if check_stop_file(stop_file):
            log_event("Stop file detected; pausing campaign")
            client.lifecycle(campaign_id, action="pause")
            break

        # Check total attempt budget (artifact already includes current-run attempts)
        total_attempts = count_attempts(campaign_id)
        if total_attempts >= max_attempts:
            log_event(f"Total attempt budget exhausted ({max_attempts})")
            log_alert("Budget reached; pausing campaign")
            client.lifecycle(campaign_id, action="pause")
            break

        # Check heartbeat
        now = time.time()
        if now - state.last_heartbeat >= heartbeat_s:
            log_heartbeat(f"Campaign {campaign_id} alive; attempted={total_attempts}/{max_attempts}")
            state.last_heartbeat = now

        # Ask server for next action
        try:
            decision = client.next_action(campaign_id)
        except (BoMcpClientError, BoMcpOperationError) as e:
            log_alert(f"Failed to get next action: {e}")
            time.sleep(poll_s)
            continue

        action = decision.get("action")
        reason = decision.get("reason", "")
        status = decision.get("status", "unknown")
        n_results = decision.get("n_results", 0)
        iteration = decision.get("iteration", 0)

        log_event(f"Server decision: action={action}, reason={reason}, status={status}, iter={iteration}, results={n_results}")

        # Auto-resume if campaign is paused
        if status == "paused" and action == "review_campaign_status":
            log_event("Campaign is paused; resuming automatically")
            client.lifecycle(campaign_id, action="resume")
            time.sleep(2.0)  # Give server time to process resume
            continue

        # Check if server recommends action other than generating suggestions
        if action != "bo_generate_suggestions":
            log_event(f"Server recommends action: {action} ({reason})")
            if action in ("pause", "terminate", "completed", "budget_exceeded"):
                break
            if action == "bo_submit_results":
                # Reconcile pending suggestions with artifact/results
                try:
                    reconcile_pending_suggestions(client, campaign_id)
                except (BoMcpClientError, BoMcpOperationError) as e:
                    log_alert(f"Failed to reconcile pending suggestions: {e}")
                # After reconciliation, continue loop to get fresh decision
                time.sleep(1.0)
                continue
            # For other actions, wait and retry
            time.sleep(poll_s)
            continue

        # Generate suggestions (batch_size=1 per iteration)
        try:
            gen_response = client.generate_suggestions(campaign_id, batch_size=1)
        except (BoMcpClientError, BoMcpOperationError) as e:
            log_alert(f"Failed to generate suggestions: {e}")
            time.sleep(poll_s)
            continue

        suggestions = gen_response.get("suggestions", [])
        if not suggestions:
            log_alert("No suggestions generated; waiting")
            time.sleep(poll_s)
            continue

        suggestion = suggestions[0]
        suggestion_id = suggestion["suggestion_id"]
        param_values = suggestion["parameter_values"]

        log_event(f"Received suggestion {suggestion_id}: {param_values}")

        # Validate suggestion
        if not validate_candidate(param_values):
            log_alert(f"Invalid suggestion from BO: {param_values}")
            client.update_suggestion_status(suggestion_id, "rejected")
            continue

        # Evaluate candidate via oracle
        log_event(f"Evaluating candidate via oracle API...")
        eval_results = evaluate_batch([param_values])
        eval_result = eval_results[0]
        state.evaluated.append(eval_result)

        # Record attempt in artifact (for budget tracking across resumes)
        attempt_record = {
            "suggestion_id": suggestion_id,
            "candidate": param_values,
            "yield": eval_result["yield"],
            "status": eval_result["status"],
            "error": eval_result["error"],
            "elapsed_s": eval_result["elapsed_s"],
            "timestamp": time.time(),
        }
        append_attempt(campaign_id, attempt_record)

        # Log result
        if eval_result["status"] == "success":
            log_result(f"Yield: {eval_result['yield']:.2f}% | {param_values}")
        else:
            log_alert(f"Evaluation failed: {eval_result['error']} | {param_values}")

        # Submit successful results to BO-MCP
        if eval_result["status"] == "success":
            try:
                submit_results(client, campaign_id, [eval_result])
                state.submitted_suggestion_ids.add(suggestion_id)
            except (BoMcpClientError, BoMcpOperationError) as e:
                log_alert(f"Result submission failed: {e}")
                # Don't mark suggestion as rejected; let server handle it
        else:
            # Mark failed suggestion as rejected so BO doesn't retry same point
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                log_event(f"Marked suggestion {suggestion_id} as rejected")
            except (BoMcpClientError, BoMcpOperationError) as e:
                log_alert(f"Failed to update suggestion status: {e}")

        # Brief pause to avoid hammering the oracle
        time.sleep(1.0)


def create_or_resume_campaign(
    client: BoMcpClient,
    campaign_id: str | None = None,
) -> str:
    """Create a new campaign or return existing campaign ID."""
    if campaign_id:
        # Verify campaign exists and has our marker
        try:
            campaign = client.get_campaign(campaign_id)
            if MARKER not in campaign.get("name", ""):
                log_alert(f"Campaign {campaign_id} does not have required marker {MARKER}")
            log_event(f"Resuming existing campaign: {campaign_id}")
            return campaign_id
        except (BoMcpClientError, BoMcpOperationError) as e:
            log_alert(f"Failed to get campaign {campaign_id}: {e}")
            raise

    # Create new campaign
    intake = build_intake()
    validate_intake(intake)

    idempotency_key = make_idempotency_key("create", MARKER, NONCE)
    try:
        response = client.create_campaign(intake, idempotency_key=idempotency_key)
        new_campaign_id = response.get("campaign_id")
        if not new_campaign_id:
            raise BoMcpOperationError("No campaign_id in response", response)
        log_event(f"Created new campaign: {new_campaign_id}")
        return new_campaign_id
    except BoMcpOperationError as e:
        if e.payload.get("idempotency_replay"):
            # Campaign already exists, find it
            log_event("Campaign creation replayed; querying for existing campaign")
            # We'd need to query campaigns to find it, but for simplicity error out
            raise BoMcpClientError("Idempotency replay but no campaign_id returned")
        raise


def run_campaign(
    campaign_id: str | None = None,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    poll_s: int = DEFAULT_POLL_S,
    heartbeat_s: int = DEFAULT_HEARTBEAT_S,
    stop_file: str = DEFAULT_STOP_FILE,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Run the direct arylation BO campaign.

    Enforces exactly 60 total attempted oracle evaluations (including failures) across all runs/resumes.
    Returns complete attempt history from artifact for final reporting.

    Returns:
        Tuple of (campaign_id, all_attempts)
    """
    # Initialize Logfire
    try:
        from grafico.core.logfire_config import configure_logfire
        configure_logfire()
        logfire.instrument_requests()
    except Exception:
        pass  # Logfire optional

    log_event(f"Direct Arylation BO Campaign starting (marker={MARKER}, nonce={NONCE})")

    # Initialize BO-MCP client
    try:
        client = BoMcpClient.from_env()
    except BoMcpClientError as e:
        log_alert(f"Failed to initialize BO-MCP client: {e}")
        raise

    # Create or resume campaign
    final_campaign_id = create_or_resume_campaign(client, campaign_id)
    state = CampaignState(final_campaign_id)

    # If resuming, load existing attempt history from artifact
    if campaign_id:
        prior_attempts = get_attempt_history(final_campaign_id)
        log_event(f"Loaded {len(prior_attempts)} prior attempts from artifact")
        # Note: We track these separately from state.evaluated (which is this run only)
        # The budget check uses count_attempts() which reads from artifact

    # Run optimization loop
    stop_path = Path(stop_file).resolve()
    run_optimization_loop(
        client,
        final_campaign_id,
        state,
        max_attempts=max_attempts,
        poll_s=poll_s,
        heartbeat_s=heartbeat_s,
        stop_file=stop_path,
    )

    # Final report: use complete attempt history from artifact
    all_attempts = get_attempt_history(final_campaign_id)
    summary = compute_summary(all_attempts)
    print_campaign_report(final_campaign_id, all_attempts, summary)
    print_final_summary_line(final_campaign_id, summary)

    # Pause campaign at end (don't terminate)
    try:
        current_status = client.get_campaign(final_campaign_id).get("status")
        if current_status == "running":
            client.lifecycle(final_campaign_id, action="pause")
            log_event("Campaign paused for resumption")
    except (BoMcpClientError, BoMcpOperationError) as e:
        log_alert(f"Failed to pause campaign: {e}")

    return final_campaign_id, all_attempts