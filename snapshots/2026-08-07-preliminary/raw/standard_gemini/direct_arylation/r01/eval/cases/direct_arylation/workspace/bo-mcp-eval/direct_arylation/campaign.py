# Campaign orchestration module for direct arylation campaign
import os
import time
import json
import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError
from direct_arylation.intake import build_intake
from direct_arylation.evaluation import evaluate_candidate
from direct_arylation.objective import extract_objective, report_result

# Exact campaign ownership marker
CAMPAIGN_MARKER = "akg-eval-c3e0d2ed3ebe4370ba327899b1a83fed"
# User cache-buster nonce
NONCE = "bc27a984-bcee-47bd-8b53-bbd5d03f3b3f"

def run_campaign_loop(
    campaign_id: str | None = None,
    stop_file: str = "STOP",
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    max_attempts: int = 60,
    results_file: str = "direct_arylation_results.json"
):
    """Orchestrate the BO-MCP campaign loop."""
    logfire.info("Starting direct arylation campaign loop. Nonce: {nonce}", nonce=NONCE)
    
    client = BoMcpClient.from_env()
    
    # 1. Resolve or create campaign
    if not campaign_id:
        campaign_name = f"Direct Arylation Optimization {CAMPAIGN_MARKER}"
        intake = build_intake(campaign_name)
        
        # Validate intake first
        try:
            client.validate_intake(intake)
            logfire.info("Campaign intake validated successfully.")
        except Exception as e:
            print(f"[ALERT] Campaign intake validation failed: {e}", flush=True)
            raise
            
        # Create campaign
        idempotency_key = client.make_idempotency_key("create", campaign_name)
        try:
            resp = client.create_campaign(intake, idempotency_key=idempotency_key)
            campaign_id = resp["campaign_id"]
            print(f"[EVENT] Created new campaign with ID: {campaign_id}", flush=True)
        except Exception as e:
            print(f"[ALERT] Failed to create campaign: {e}", flush=True)
            raise
    else:
        print(f"[EVENT] Resuming existing campaign with ID: {campaign_id}", flush=True)
        # Verify campaign exists
        try:
            client.get_campaign(campaign_id)
        except Exception as e:
            print(f"[ALERT] Failed to retrieve campaign {campaign_id}: {e}", flush=True)
            raise

    # Load existing local results if any (for reporting at the end)
    local_results = []
    if os.path.exists(results_file):
        try:
            with open(results_file, "r") as f:
                local_results = json.load(f)
            logfire.info("Loaded {count} existing local results.", count=len(local_results))
        except Exception as e:
            logfire.warning("Failed to load local results file: {e}", e=e)

    last_heartbeat = time.time()
    
    # 2. Main optimization loop
    while True:
        # Check stop file
        if os.path.exists(stop_file):
            print(f"[EVENT] Stop file '{stop_file}' detected. Shutting down gracefully.", flush=True)
            try:
                os.remove(stop_file)
            except Exception as e:
                logfire.warning("Failed to remove stop file: {e}", e=e)
            break
            
        # Check heartbeat
        now = time.time()
        if now - last_heartbeat >= heartbeat_s:
            print(f"[HEARTBEAT] Campaign {campaign_id} is active.", flush=True)
            last_heartbeat = now

        # Query suggestions to count attempts
        try:
            suggestions = client.query_suggestions(campaign_id)
        except Exception as e:
            print(f"[ALERT] Failed to query suggestions: {e}", flush=True)
            time.sleep(10)
            continue

        # Count attempts (completed or rejected suggestions)
        completed_attempts = [s for s in suggestions if s["status"] in ("completed", "rejected")]
        attempts_count = len(completed_attempts)
        
        logfire.info("Current attempts count: {count}/{max_attempts}", count=attempts_count, max_attempts=max_attempts)
        
        if attempts_count >= max_attempts:
            print(f"[EVENT] Reached maximum attempted evaluations budget ({max_attempts}). Stopping.", flush=True)
            break

        # Get next action from server
        try:
            decision = client.next_action(campaign_id)
        except Exception as e:
            print(f"[ALERT] Failed to get next action: {e}", flush=True)
            time.sleep(10)
            continue

        action = decision.get("action")
        status = decision.get("status")
        
        logfire.info("Server next action: {action}, status: {status}", action=action, status=status)
        
        if status == "paused":
            print(f"[EVENT] Campaign is paused. Resuming campaign...", flush=True)
            try:
                client.lifecycle(campaign_id, action="resume")
                continue
            except Exception as e:
                print(f"[ALERT] Failed to resume campaign: {e}", flush=True)
                time.sleep(10)
                continue
                
        if status == "completed":
            print(f"[EVENT] Campaign is completed. Reopening campaign...", flush=True)
            try:
                client.lifecycle(campaign_id, action="reopen")
                continue
            except Exception as e:
                print(f"[ALERT] Failed to reopen campaign: {e}", flush=True)
                time.sleep(10)
                continue
                
        if action != "bo_generate_suggestions":
            print(f"[EVENT] Server returned action '{action}' (status: {status}). Stopping loop.", flush=True)
            break

        # Find or generate suggestion
        pending = [s for s in suggestions if s["status"] == "pending"]
        if pending:
            suggestion = pending[0]
            logfire.info("Reusing pending suggestion: {id}", id=suggestion["suggestion_id"])
        else:
            try:
                gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
                if not gen_resp.get("success"):
                    print(f"[ALERT] Suggestion generation failed: {gen_resp.get('errors')}", flush=True)
                    time.sleep(10)
                    continue
                suggestion = gen_resp["suggestions"][0]
                logfire.info("Generated new suggestion: {id}", id=suggestion["suggestion_id"])
            except Exception as e:
                print(f"[ALERT] Failed to generate suggestions: {e}", flush=True)
                time.sleep(10)
                continue

        suggestion_id = suggestion["suggestion_id"]
        parameter_values = suggestion["parameter_values"]

        # Evaluate candidate
        print(f"[EVENT] Evaluating candidate {attempts_count + 1}/{max_attempts}: {parameter_values}", flush=True)
        
        try:
            eval_result = evaluate_candidate(parameter_values)
            yield_val = extract_objective(eval_result)
            
            # Submit result to BO-MCP
            idempotency_key = client.make_idempotency_key("submit", suggestion_id)
            result_payload = {
                "parameter_values": parameter_values,
                "objective_values": {"yield": yield_val},
                "suggestion_id": suggestion_id
            }
            
            try:
                client.submit_results(campaign_id, results=[result_payload], idempotency_key=idempotency_key)
                print(f"[EVENT] Submitted result for suggestion {suggestion_id}", flush=True)
                
                # Record locally
                record = {
                    "parameter_values": parameter_values,
                    "objective_values": {"yield": yield_val},
                    "status": "success",
                    "suggestion_id": suggestion_id
                }
                local_results.append(record)
                report_result(parameter_values, yield_val, "success")
                
            except Exception as e:
                print(f"[ALERT] Failed to submit result to BO-MCP: {e}", flush=True)
                # If submission failed, we don't count it as a completed attempt on the server yet,
                # but we should retry or handle it.
                time.sleep(10)
                continue
                
        except Exception as e:
            print(f"[ALERT] Evaluation failed for candidate {parameter_values}: {e}", flush=True)
            
            # Update suggestion status to rejected
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                print(f"[EVENT] Rejected suggestion {suggestion_id} due to evaluation failure", flush=True)
            except Exception as re:
                print(f"[ALERT] Failed to reject suggestion {suggestion_id}: {re}", flush=True)
                
            # Record failure locally
            record = {
                "parameter_values": parameter_values,
                "objective_values": None,
                "status": "failed",
                "suggestion_id": suggestion_id
            }
            local_results.append(record)
            report_result(parameter_values, 0.0, "failed")

        # Save local results file
        try:
            with open(results_file, "w") as f:
                json.dump(local_results, f, indent=2)
        except Exception as e:
            logfire.warning("Failed to save local results file: {e}", e=e)

        # Sleep before next iteration
        logfire.info("Sleeping for {poll_s} seconds...", poll_s=poll_s)
        time.sleep(poll_s)

    # 3. End-of-run reporting
    print("\n=== CAMPAIGN SUMMARY ===", flush=True)
    successful_evals = [r for r in local_results if r["status"] == "success"]
    failed_evals = [r for r in local_results if r["status"] == "failed"]
    
    print(f"Campaign ID: {campaign_id}", flush=True)
    print(f"Attempted evaluations: {len(local_results)}", flush=True)
    print(f"Successful evaluations: {len(successful_evals)}", flush=True)
    print(f"Failed evaluations: {len(failed_evals)}", flush=True)
    
    if successful_evals:
        best_record = max(successful_evals, key=lambda r: r["objective_values"]["yield"])
        print(f"Best measured yield: {best_record['objective_values']['yield']}%", flush=True)
        print(f"Best reaction conditions: {best_record['parameter_values']}", flush=True)
    else:
        print("No successful evaluations recorded.", flush=True)
    print("========================\n", flush=True)
    
    # Pause campaign at the end of invocation
    try:
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] Paused campaign {campaign_id}", flush=True)
    except Exception as e:
        logfire.warning("Failed to pause campaign: {e}", e=e)
        
    return campaign_id
