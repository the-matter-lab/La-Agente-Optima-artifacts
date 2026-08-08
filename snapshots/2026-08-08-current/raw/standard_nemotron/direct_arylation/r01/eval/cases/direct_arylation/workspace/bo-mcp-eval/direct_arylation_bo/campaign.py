"""Campaign orchestration module for direct arylation BO campaign."""

import os
import time
import uuid
from pathlib import Path
from typing import Any

import logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from direct_arylation_bo.evaluator import evaluate_candidate, write_attempt_artifact
from direct_arylation_bo.intake import build_intake, CAMPAIGN_NAME
from direct_arylation_bo.search_space import get_search_space_size


MAX_ATTEMPTS = 60


def log_event(tag: str, message: str, **kwargs: Any) -> None:
    """Log a tagged event for the parent monitor."""
    logfire.info(f"[{tag}] {message}", **kwargs)
    print(f"[{tag}] {message}", flush=True)


def make_idempotency_key(prefix: str, *parts: str) -> str:
    """Generate an idempotency key with a random suffix."""
    joined = "-".join(part.replace("/", "_") for part in parts if part)
    return f"{prefix}-{joined}-{uuid.uuid4().hex[:10]}"


def evaluate_and_submit(
    client: BoMcpClient,
    campaign_id: str,
    suggestion: dict[str, Any],
    base_attempt_number: int,
    attempt_count: int,
    artifact_dir: Path,
    oracle_timeout_s: float,
    best_yield: float,
    best_params: dict[str, Any] | None,
    all_evaluated: list[dict[str, Any]],
    success_count: int,
) -> tuple[int, int, float, dict[str, Any] | None]:
    """Evaluate a suggestion and submit result. Returns updated (attempt_count, success_count, best_yield, best_params)."""
    suggestion_id = suggestion["suggestion_id"]
    params = suggestion["parameter_values"]
    global_attempt_number = base_attempt_number + attempt_count + 1

    log_event("EVENT", f"Evaluating attempt {global_attempt_number}: {params}")

    success, yield_value, error_msg = evaluate_candidate(params, timeout_s=oracle_timeout_s)
    attempt_count += 1

    evaluated_record = {
        "attempt_number": global_attempt_number,
        "suggestion_id": suggestion_id,
        "parameter_values": params,
        "success": success,
        "yield": yield_value,
        "error": error_msg,
    }
    all_evaluated.append(evaluated_record)

    write_attempt_artifact(artifact_dir, global_attempt_number, params, success, yield_value, error_msg)

    if success and yield_value is not None:
        success_count += 1
        log_event("RESULT", f"Attempt {global_attempt_number}: yield={yield_value:.2f}% {params}")

        if yield_value > best_yield:
            best_yield = yield_value
            best_params = params.copy()

        submit_key = make_idempotency_key("submit", campaign_id, str(global_attempt_number))
        submit_response = client.submit_results(
            campaign_id,
            results=[{
                "suggestion_id": suggestion_id,
                "parameter_values": params,
                "objective_values": {"yield": yield_value},
            }],
            idempotency_key=submit_key,
        )
        if not submit_response.get("success", True):
            log_event("ALERT", f"Result submission failed: {submit_response.get('errors')}")
    else:
        log_event("ALERT", f"Attempt {global_attempt_number} failed: {error_msg}")
        client.update_suggestion_status(suggestion_id, "failed")

    return attempt_count, success_count, best_yield, best_params


def run_campaign(
    *,
    campaign_id: str | None = None,
    artifact_dir: Path,
    stop_file: Path,
    poll_interval_s: int = 180,
    heartbeat_interval_s: int = 1800,
    oracle_timeout_s: float = 15.0,
) -> dict[str, Any]:
    """
    Run the BO campaign loop.

    Args:
        campaign_id: Existing campaign ID to resume, or None to create new.
        artifact_dir: Directory for per-attempt artifacts.
        stop_file: Path to stop file; if exists, pause after current iteration.
        poll_interval_s: Seconds between next_action checks.
        heartbeat_interval_s: Seconds between heartbeat logs.
        oracle_timeout_s: Timeout for oracle calls.

    Returns:
        Summary dict with best conditions, yield, counts, and all evaluated candidates.
    """
    client = BoMcpClient.from_env()

    # Create or resume campaign
    if campaign_id is None:
        log_event("EVENT", "Creating new campaign")
        intake = build_intake()
        validate_key = make_idempotency_key("validate", CAMPAIGN_NAME)
        try:
            client.validate_intake(intake)
        except BoMcpOperationError as exc:
            log_event("ALERT", f"Intake validation failed: {exc}")
            raise

        create_key = make_idempotency_key("create", CAMPAIGN_NAME)
        response = client.create_campaign(intake, idempotency_key=create_key)
        campaign_id = response["campaign_id"]
        log_event("EVENT", f"Created campaign {campaign_id}")
    else:
        log_event("EVENT", f"Resuming campaign {campaign_id}")
        # If campaign is paused, resume it
        status = client.get_campaign(campaign_id).get("status")
        if status == "paused":
            log_event("EVENT", "Campaign is paused, resuming...")
            client.lifecycle(campaign_id, action="resume")

    # Track state
    # Get existing results count for global attempt numbering
    existing_results = client.get_results(campaign_id)
    base_attempt_number = len(existing_results)
    log_event("EVENT", f"Campaign has {base_attempt_number} existing results")

    attempt_count = 0
    success_count = 0
    all_evaluated: list[dict[str, Any]] = []
    best_yield = -1.0
    best_params: dict[str, Any] | None = None
    last_heartbeat = time.time()

    while attempt_count < MAX_ATTEMPTS:
        # Check stop file
        if stop_file.exists():
            log_event("EVENT", f"Stop file detected at {stop_file}, pausing campaign")
            stop_file.unlink(missing_ok=True)
            client.lifecycle(campaign_id, action="pause")
            break

        # Heartbeat
        if time.time() - last_heartbeat >= heartbeat_interval_s:
            log_event("HEARTBEAT", f"Campaign {campaign_id} running, attempt {attempt_count}/{MAX_ATTEMPTS}")
            last_heartbeat = time.time()

        # Ask server for next action
        decision = client.next_action(campaign_id)
        action = decision.get("action")
        reason = decision.get("reason", "")
        n_results = decision.get("n_results", 0)
        iteration = decision.get("iteration", 0)

        log_event("EVENT", f"Next action: {action} (reason: {reason}, results: {n_results}, iteration: {iteration})")

        # Handle paused campaign - resume it
        if action == "review_campaign_status" and "paused" in reason.lower():
            log_event("EVENT", "Campaign paused, resuming...")
            client.lifecycle(campaign_id, action="resume")
            continue

        if action == "bo_submit_results":
            # There are pending suggestions awaiting results - evaluate them
            log_event("EVENT", "Pending suggestions detected, evaluating...")
            pending_suggestions = client.query_suggestions(campaign_id, status_filter="pending")
            if pending_suggestions:
                for suggestion in pending_suggestions:
                    if attempt_count >= MAX_ATTEMPTS:
                        log_event("EVENT", "Reached max attempts limit")
                        break
                    attempt_count, success_count, best_yield, best_params = evaluate_and_submit(
                        client, campaign_id, suggestion, base_attempt_number, attempt_count,
                        artifact_dir, oracle_timeout_s, best_yield, best_params,
                        all_evaluated, success_count
                    )
                # After submitting pending results, continue to next action check
                time.sleep(min(poll_interval_s, 5))
                continue
            else:
                log_event("ALERT", "bo_submit_results action but no pending suggestions found")

        if action != "bo_generate_suggestions":
            log_event("EVENT", f"Campaign stopping: {action} - {reason}")
            if action in ("completed", "terminated", "paused", "budget_exceeded", "converged"):
                client.lifecycle(campaign_id, action="pause")
            break

        # Generate suggestions
        gen_key = make_idempotency_key("generate", campaign_id, str(iteration))
        try:
            gen_response = client.generate_suggestions(campaign_id, batch_size=1)
        except BoMcpOperationError as exc:
            log_event("ALERT", f"Suggestion generation failed: {exc}")
            # Check if campaign is actually done
            if "stopping criteria" in str(exc).lower() or "budget" in str(exc).lower():
                client.lifecycle(campaign_id, action="pause")
                break
            raise

        if not gen_response.get("success", True):
            errors = gen_response.get("errors", [])
            log_event("ALERT", f"Suggestion generation rejected: {errors}")
            if any("stopping" in e.lower() or "budget" in e.lower() for e in errors):
                client.lifecycle(campaign_id, action="pause")
                break
            raise RuntimeError(f"Generation failed: {errors}")

        suggestions = gen_response.get("suggestions", [])
        if not suggestions:
            log_event("ALERT", "No suggestions returned")
            break

        # Evaluate each suggestion (batch_size=1 so just one)
        for suggestion in suggestions:
            if attempt_count >= MAX_ATTEMPTS:
                log_event("EVENT", "Reached max attempts limit")
                break
            attempt_count, success_count, best_yield, best_params = evaluate_and_submit(
                client, campaign_id, suggestion, base_attempt_number, attempt_count,
                artifact_dir, oracle_timeout_s, best_yield, best_params,
                all_evaluated, success_count
            )

        # Brief pause between iterations to respect poll interval
        time.sleep(min(poll_interval_s, 5))

    # Final summary
    summary = {
        "campaign_id": campaign_id,
        "campaign_name": CAMPAIGN_NAME,
        "total_attempts": attempt_count,
        "successful_evaluations": success_count,
        "best_yield": best_yield if best_params else None,
        "best_conditions": best_params,
        "all_evaluated": all_evaluated,
    }

    log_event("EVENT", f"Campaign complete: {success_count}/{attempt_count} successful, best yield: {best_yield:.2f}%" if best_params else "No successful evaluations")

    return summary