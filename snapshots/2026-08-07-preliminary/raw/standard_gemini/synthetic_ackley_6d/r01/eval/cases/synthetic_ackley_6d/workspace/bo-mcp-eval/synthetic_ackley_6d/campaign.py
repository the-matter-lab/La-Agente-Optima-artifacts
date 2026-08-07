import os
import time
import math
import logging
import logfire
from typing import Optional, Dict, Any

from domains.bo_mcp.client import BoMcpClient
from synthetic_ackley_6d.intake import create_campaign_intake
from synthetic_ackley_6d.evaluation import evaluate_ackley_6d
from synthetic_ackley_6d.reporting import (
    append_to_results_artifact,
    load_results_artifact,
    generate_final_report
)

# Configure logging
logger = logging.getLogger("synthetic_ackley_6d")

def is_duplicate(p1: dict, p2: dict, tol: float = 1e-7) -> bool:
    if set(p1.keys()) != set(p2.keys()):
        return False
    for k in p1:
        if not math.isclose(float(p1[k]), float(p2[k]), rel_tol=tol, abs_tol=tol):
            return False
    return True

def has_duplicate(suggested_params: dict, evaluated_list: list, tol: float = 1e-7) -> bool:
    for eval_item in evaluated_list:
        if is_duplicate(suggested_params, eval_item, tol):
            return True
    return False


def run_campaign_loop(
    client: BoMcpClient,
    campaign_id: Optional[str] = None,
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    stop_file: str = "STOP",
    artifact_dir: str = "artifacts",
    budget: int = 60,
) -> str:
    """
    Orchestrates the BO-MCP optimization loop for the 6D Ackley surface.
    """
    # 1. Resolve or create campaign
    if campaign_id:
        logfire.info("Resuming existing campaign", campaign_id=campaign_id)
        print(f"[EVENT] Resuming campaign {campaign_id}")
        
        # Check campaign status
        try:
            campaign = client.get_campaign(campaign_id)
            status = campaign.get("status")
            logfire.info("Current campaign status", status=status)
            
            if status == "paused":
                print(f"[EVENT] Campaign is paused. Resuming...")
                client.lifecycle(campaign_id, action="resume")
            elif status == "completed" or status == "terminated":
                print(f"[EVENT] Campaign is {status}. Reopening...")
                client.lifecycle(campaign_id, action="reopen")
        except Exception as e:
            logfire.error("Failed to get or resume campaign", error=str(e))
            print(f"[ALERT] Failed to resume campaign {campaign_id}: {e}")
            raise
    else:
        logfire.info("Creating a new campaign")
        print("[EVENT] Creating a new campaign...")
        intake = create_campaign_intake()
        
        # Validate intake
        try:
            client.validate_intake(intake)
            logfire.info("Intake validation successful")
        except Exception as e:
            logfire.error("Intake validation failed", error=str(e))
            print(f"[ALERT] Campaign intake validation failed: {e}")
            raise
            
        # Create campaign
        idempotency_key = client.make_idempotency_key("ackley", "create")
        try:
            response = client.create_campaign(intake, idempotency_key=idempotency_key)
            campaign_id = response.get("campaign_id")
            if not campaign_id:
                raise ValueError(f"No campaign_id returned in response: {response}")
            logfire.info("Campaign created successfully", campaign_id=campaign_id)
            print(f"[EVENT] Created campaign with ID: {campaign_id}")
            print(f"BO_MCP_CAMPAIGN_ID={campaign_id}")
        except Exception as e:
            logfire.error("Campaign creation failed", error=str(e))
            print(f"[ALERT] Failed to create campaign: {e}")
            raise

    # 2. Optimization loop
    last_heartbeat_time = time.time()
    
    while True:
        # Check stop file at the top of each loop iteration
        if os.path.exists(stop_file):
            print(f"[EVENT] Stop file '{stop_file}' detected. Initiating graceful shutdown.")
            try:
                os.remove(stop_file)
                logfire.info("Stop file removed")
            except Exception as e:
                logfire.warning("Failed to remove stop file", error=str(e))
                
            # Pause the campaign
            try:
                client.lifecycle(campaign_id, action="pause")
                print(f"[EVENT] Campaign {campaign_id} paused successfully.")
            except Exception as e:
                print(f"[ALERT] Failed to pause campaign {campaign_id}: {e}")
            break
            
        # Check heartbeat
        current_time = time.time()
        if current_time - last_heartbeat_time >= heartbeat_s:
            print(f"[HEARTBEAT] Campaign {campaign_id} is active.")
            last_heartbeat_time = current_time
            
        # Check budget
        results = load_results_artifact(artifact_dir)
        eval_count = len(results)
        if eval_count >= budget:
            print(f"[EVENT] Evaluation budget of {budget} reached. Stopping loop.")
            # Terminate/complete the campaign
            try:
                client.lifecycle(campaign_id, action="terminate")
                print(f"[EVENT] Campaign {campaign_id} terminated/completed successfully.")
            except Exception as e:
                print(f"[ALERT] Failed to terminate campaign {campaign_id}: {e}")
            break
            
        # Query next action from server
        try:
            decision = client.next_action(campaign_id)
            action = decision.get("action")
            logfire.info("Next action decision", action=action, decision=decision)
        except Exception as e:
            logfire.error("Failed to query next action", error=str(e))
            print(f"[ALERT] Failed to query next action for campaign {campaign_id}: {e}")
            # Sleep and retry
            time.sleep(10)
            continue
            
        if action != "bo_generate_suggestions":
            print(f"[EVENT] Server returned action '{action}'. Stopping loop.")
            break
            
        # Generate suggestions
        print(f"[EVENT] Generating suggestion for evaluation {eval_count + 1}...")
        try:
            suggestion_response = client.generate_suggestions(campaign_id, batch_size=1)
            suggestions = suggestion_response.get("suggestions", [])
            if not suggestions:
                print("[ALERT] No suggestions returned by server.")
                time.sleep(10)
                continue
            suggestion = suggestions[0]
            suggestion_id = suggestion.get("suggestion_id")
            parameter_values = suggestion.get("parameter_values")
            logfire.info("Generated suggestion", suggestion_id=suggestion_id, parameter_values=parameter_values)
        except Exception as e:
            logfire.error("Failed to generate suggestions", error=str(e))
            print(f"[ALERT] Failed to generate suggestions: {e}")
            time.sleep(10)
            continue

        # Build list of already evaluated coordinates
        results = load_results_artifact(artifact_dir)
        evaluated_points = [r.get("parameter_values", {}) for r in results if r.get("status") == "success"]
        try:
            server_results = client.get_results(campaign_id)
            for r in server_results:
                params = r.get("parameter_values", {})
                if not has_duplicate(params, evaluated_points):
                    evaluated_points.append(params)
        except Exception as e:
            logfire.warning("Failed to fetch results from server for duplicate check", error=str(e))
            
        # Check for duplicates
        if has_duplicate(parameter_values, evaluated_points):
            print(f"[ALERT] Suggested candidate is a duplicate of an already evaluated point. Rejecting suggestion {suggestion_id}.")
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                logfire.info("Duplicate suggestion rejected successfully", suggestion_id=suggestion_id)
            except Exception as e:
                logfire.error("Failed to reject duplicate suggestion", error=str(e))
                print(f"[ALERT] Failed to reject duplicate suggestion {suggestion_id}: {e}")
            # Sleep briefly and continue the loop to generate a new suggestion
            time.sleep(1)
            continue

            
        # Evaluate candidate
        print(f"[EVENT] Evaluating candidate {eval_count + 1}...")
        status = "success"
        failure_reason = None
        surf_resp = None
        raw_resp = None
        
        try:
            surf_resp, raw_resp = evaluate_ackley_6d(parameter_values)
            logfire.info("Evaluation success", surface_response=surf_resp, raw_response=raw_resp)
        except Exception as e:
            status = "failed"
            failure_reason = str(e)
            logfire.error("Evaluation failed", error=str(e))
            print(f"[ALERT] Evaluation failed for candidate {eval_count + 1}: {e}")
            
        # Submit results or reject suggestion
        if status == "success":
            # Submit to BO-MCP
            idempotency_key = client.make_idempotency_key("ackley", "submit", str(eval_count + 1))
            results_payload = [
                {
                    "objective_values": {"surface_response": surf_resp},
                    "parameter_values": parameter_values,
                    "suggestion_id": suggestion_id
                }
            ]
            try:
                client.submit_results(campaign_id, results=results_payload, idempotency_key=idempotency_key)
                logfire.info("Results submitted successfully")
                print(f"[RESULT] Evaluation {eval_count + 1}: success. Surface response: {surf_resp:.6f}, Raw response: {raw_resp:.6f}")
            except Exception as e:
                logfire.error("Failed to submit results", error=str(e))
                print(f"[ALERT] Failed to submit results to BO-MCP: {e}")
                # We will still record it locally as failed or retry?
                # Let's treat it as a failure to submit
                status = "failed"
                failure_reason = f"Submission failed: {e}"
        else:
            # Reject suggestion on BO-MCP
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                logfire.info("Suggestion rejected successfully", suggestion_id=suggestion_id)
            except Exception as e:
                logfire.error("Failed to reject suggestion", error=str(e))
                print(f"[ALERT] Failed to reject suggestion {suggestion_id}: {e}")
                
        # Append to local results artifact
        append_to_results_artifact(
            evaluation_index=eval_count + 1,
            parameter_values=parameter_values,
            objective_values={"surface_response": surf_resp} if surf_resp is not None else {},
            status=status,
            failure_reason=failure_reason,
            raw_response=raw_resp,
            artifact_dir=artifact_dir
        )
        
        # Sleep briefly to avoid hammering the server
        time.sleep(1)
        
    # 3. Final reporting
    generate_final_report(artifact_dir)
    return campaign_id
