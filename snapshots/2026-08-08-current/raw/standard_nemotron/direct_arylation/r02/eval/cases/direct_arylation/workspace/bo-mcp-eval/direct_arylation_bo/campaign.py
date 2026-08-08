"""Campaign orchestration for the direct arylation BO-MCP campaign."""

import os
import uuid
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .intake import build_intake, validate_intake_structure
from .evaluation import evaluate_candidate, OracleEvaluationError
from .reporting import generate_final_report, print_final_summary


def run_campaign(
    *,
    campaign_id: str | None = None,
    batch_size: int = 1,
    max_evaluations: int = 60,
    artifacts_dir: Path,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Run the direct arylation BO campaign.

    Args:
        campaign_id: Existing campaign ID to resume, or None to create new
        batch_size: Number of suggestions per iteration
        max_evaluations: Maximum number of oracle evaluations this invocation
        artifacts_dir: Directory for artifact files
        timeout_s: BO-MCP client timeout

    Returns:
        Final campaign summary dictionary
    """
    client = BoMcpClient.from_env(timeout_s=timeout_s)

    # Create or resume campaign
    if campaign_id is None:
        intake = build_intake(batch_size=batch_size, random_seed=42)
        validate_intake_structure(intake)

        # Validate intake with server first
        client.validate_intake(intake)

        # Create campaign with idempotency key
        idempotency_key = f"create-{uuid.uuid4().hex[:12]}"
        create_response = client.create_campaign(intake, idempotency_key=idempotency_key)
        campaign_id = create_response["campaign_id"]
        print(f"[EVENT] Created campaign {campaign_id}")
    else:
        print(f"[EVENT] Resuming campaign {campaign_id}")

    # Track all evaluations for final reporting
    all_evaluations: list[dict[str, Any]] = []

    # Load any existing results from server for reporting continuity
    try:
        existing_results = client.get_results(campaign_id)
        for r in existing_results:
            all_evaluations.append({
                "candidate": r["parameter_values"],
                "yield": r["objective_values"].get("yield"),
                "error": None,
                "status": "success",
            })
        print(f"[EVENT] Loaded {len(existing_results)} existing results from server")
    except Exception:
        pass  # No existing results or error reading them

    # Main optimization loop
    evaluations_this_run = 0
    while evaluations_this_run < max_evaluations:
        # Check stop file
        stop_file = Path("STOP")
        if stop_file.exists():
            print("[EVENT] Stop file detected, pausing campaign")
            stop_file.unlink()  # Remove so resume isn't blocked
            client.lifecycle(campaign_id, action="pause")
            break

        # Ask server for next action
        decision = client.next_action(campaign_id)
        action = decision.get("action")
        reason = decision.get("reason", "")
        print(f"[EVENT] Server decision: action={action}, reason={reason}, iteration={decision.get('iteration')}, n_results={decision.get('n_results')}")

        if action != "bo_generate_suggestions":
            print(f"[EVENT] Campaign stopping: {reason}")
            break

        # Generate suggestions
        gen_response = client.generate_suggestions(campaign_id, batch_size=batch_size)
        if not gen_response.get("success"):
            errors = gen_response.get("errors", [])
            print(f"[ALERT] Suggestion generation failed: {errors}")
            break

        suggestions = gen_response.get("suggestions", [])
        if not suggestions:
            print("[ALERT] No suggestions returned")
            break

        print(f"[EVENT] Generated {len(suggestions)} suggestion(s)")

        # Evaluate each suggestion
        results_to_submit = []
        for suggestion in suggestions:
            if evaluations_this_run >= max_evaluations:
                print(f"[EVENT] Reached evaluation budget ({max_evaluations}), stopping")
                break

            suggestion_id = suggestion["suggestion_id"]
            param_values = suggestion["parameter_values"]

            print(f"[EVENT] Evaluating suggestion {suggestion_id}: {param_values}")

            try:
                yield_val = evaluate_candidate(param_values)
                print(f"[RESULT] yield={yield_val:.2f}% for {suggestion_id}")

                # Record for reporting
                all_evaluations.append({
                    "candidate": param_values,
                    "yield": yield_val,
                    "error": None,
                    "status": "success",
                })

                # Prepare result for submission
                results_to_submit.append({
                    "suggestion_id": suggestion_id,
                    "parameter_values": param_values,
                    "objective_values": {"yield": yield_val},
                })

            except OracleEvaluationError as exc:
                print(f"[ALERT] Evaluation failed for {suggestion_id}: {exc}")

                # Record failure
                all_evaluations.append({
                    "candidate": param_values,
                    "yield": None,
                    "error": str(exc),
                    "status": "failed",
                })

                # Mark suggestion as failed so BO doesn't retry it
                client.update_suggestion_status(suggestion_id, "failed")

            evaluations_this_run += 1

        # Submit successful results
        if results_to_submit:
            submit_key = f"submit-{campaign_id}-{uuid.uuid4().hex[:10]}"
            try:
                submit_response = client.submit_results(
                    campaign_id,
                    results=results_to_submit,
                    idempotency_key=submit_key,
                )
                if not submit_response.get("success"):
                    print(f"[ALERT] Result submission failed: {submit_response.get('errors')}")
                else:
                    print(f"[EVENT] Submitted {len(results_to_submit)} result(s)")
            except BoMcpOperationError as exc:
                print(f"[ALERT] Result submission rejected: {exc.payload}")

        # Heartbeat
        if evaluations_this_run % 5 == 0:
            print(f"[HEARTBEAT] Completed {evaluations_this_run}/{max_evaluations} evaluations this run")

    # Pause campaign at end of invocation (unless already stopped)
    try:
        campaign_status = client.get_campaign(campaign_id).get("status")
        if campaign_status == "running":
            client.lifecycle(campaign_id, action="pause")
            print("[EVENT] Campaign paused")
    except Exception:
        pass

    # Generate final report
    summary = generate_final_report(campaign_id, all_evaluations, artifacts_dir)
    print_final_summary(summary)

    return summary