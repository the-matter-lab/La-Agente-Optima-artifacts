# direct_arylation/campaign.py

import os
import time
import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError
from .intake import create_campaign_intake
from .evaluator import evaluate_candidate
from .reporting import print_final_summary

def get_next_suggestion(client: BoMcpClient, campaign_id: str) -> dict | None:
    """Get the next suggestion, reusing pending ones if available, or generating a new one."""
    try:
        pending = client.query_suggestions(campaign_id, status_filter="pending")
        if pending:
            logfire.info("Reusing pending suggestion: {suggestion_id}", suggestion_id=pending[0]["suggestion_id"])
            return pending[0]
    except Exception as e:
        logfire.warning("Failed to query pending suggestions: {error}", error=str(e))
        
    try:
        logfire.info("Generating new suggestion...")
        resp = client.generate_suggestions(campaign_id, batch_size=1)
        if resp.get("success") and resp.get("suggestions"):
            return resp["suggestions"][0]
    except BoMcpOperationError as e:
        logfire.error("Operation error during suggestion generation: {error}", error=str(e))
    except Exception as e:
        logfire.error("Unexpected error during suggestion generation: {error}", error=str(e))
        
    return None

def run_campaign(
    campaign_id: str | None = None,
    budget: int = 60,
    stop_file: str = "STOP",
    poll_s: int = 180,
    heartbeat_s: int = 1800
) -> str:
    """Orchestrate the direct arylation optimization campaign."""
    client = BoMcpClient.from_env()
    
    # 1. Create or resume campaign
    if not campaign_id:
        intake = create_campaign_intake()
        campaign_name = intake["name"]
        idempotency_key = client.make_idempotency_key("create", campaign_name)
        
        print(f"[EVENT] Creating new campaign: {campaign_name}")
        try:
            resp = client.create_campaign(intake, idempotency_key=idempotency_key)
            campaign_id = resp["campaign_id"]
            print(f"[EVENT] Campaign created successfully. ID: {campaign_id}")
        except BoMcpOperationError as e:
            print(f"[ALERT] Failed to create campaign: {e}")
            raise
    else:
        print(f"[EVENT] Resuming existing campaign: {campaign_id}")
        # Ensure campaign is resumed/reopened if needed
        try:
            decision = client.next_action(campaign_id)
            status = decision.get("status")
            if status == "paused":
                client.lifecycle(campaign_id, action="resume")
                print("[EVENT] Campaign resumed on server.")
            elif status == "completed":
                client.lifecycle(campaign_id, action="reopen")
                print("[EVENT] Campaign reopened on server.")
        except Exception as e:
            print(f"[ALERT] Failed to check/resume campaign status: {e}")
            raise

    # 2. Initialize counts from server state
    try:
        all_suggestions = client.query_suggestions(campaign_id)
        completed_count = sum(1 for s in all_suggestions if s.get("status") == "completed")
        rejected_count = sum(1 for s in all_suggestions if s.get("status") == "rejected")
        attempted_count = completed_count + rejected_count
        successful_count = completed_count
    except Exception as e:
        print(f"[ALERT] Failed to query suggestions for initialization: {e}")
        # Fallback to results count
        try:
            results = client.get_results(campaign_id)
            successful_count = len(results)
            attempted_count = successful_count
            rejected_count = 0
        except Exception:
            successful_count = 0
            attempted_count = 0
            rejected_count = 0

    print(f"[EVENT] Campaign state: {attempted_count}/{budget} attempts completed ({successful_count} successful, {attempted_count - successful_count} failed).")
    
    last_heartbeat = time.time()
    failed_candidates = []
    
    # 3. Optimization loop
    while attempted_count < budget:
        # Check stop file
        if os.path.exists(stop_file):
            print(f"[EVENT] Stop file '{stop_file}' detected. Pausing campaign and exiting.")
            try:
                os.remove(stop_file)
            except Exception as e:
                print(f"[ALERT] Failed to remove stop file: {e}")
            
            try:
                client.lifecycle(campaign_id, action="pause")
                print("[EVENT] Campaign paused on server.")
            except Exception as e:
                print(f"[ALERT] Failed to pause campaign on server: {e}")
            break
            
        # Check heartbeat
        now = time.time()
        if now - last_heartbeat >= heartbeat_s:
            print(f"[HEARTBEAT] Liveness check. Attempted: {attempted_count}/{budget}, Successful: {successful_count}")
            last_heartbeat = now
            
        # Check next action
        try:
            decision = client.next_action(campaign_id)
            status = decision.get("status")
            action = decision.get("action")
            
            if status == "paused":
                client.lifecycle(campaign_id, action="resume")
                continue
            elif status == "completed":
                client.lifecycle(campaign_id, action="reopen")
                continue
                
            if action != "bo_generate_suggestions":
                print(f"[EVENT] Server next action is '{action}'. Stopping loop.")
                break
        except Exception as e:
            print(f"[ALERT] Failed to get next action from server: {e}")
            time.sleep(10)
            continue
            
        # Get next suggestion
        suggestion = get_next_suggestion(client, campaign_id)
        if not suggestion:
            print("[ALERT] Failed to get or generate suggestion. Retrying in 10s...")
            time.sleep(10)
            continue
            
        candidate = suggestion["parameter_values"]
        suggestion_id = suggestion["suggestion_id"]
        
        # Evaluate candidate
        attempted_count += 1
        result = evaluate_candidate(candidate)
        
        if result is not None:
            successful_count += 1
            yield_val = result["yield"]
            
            result_row = {
                "parameter_values": candidate,
                "objective_values": {"yield": yield_val},
                "suggestion_id": suggestion_id
            }
            
            idempotency_key = client.make_idempotency_key("submit", campaign_id, suggestion_id)
            try:
                client.submit_results(campaign_id, results=[result_row], idempotency_key=idempotency_key)
                print(f"[RESULT] SUCCESS | base={candidate['base']}, ligand={candidate['ligand']}, solvent={candidate['solvent']}, concentration={candidate['concentration']}, temperature_c={candidate['temperature_c']} -> Yield: {yield_val:.2f}%")
            except Exception as e:
                print(f"[ALERT] Failed to submit result to BO-MCP: {e}")
                successful_count -= 1
        else:
            # Record failure
            failed_candidates.append({
                "parameter_values": candidate,
                "status": "failed"
            })
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
                print(f"[RESULT] FAILED  | base={candidate['base']}, ligand={candidate['ligand']}, solvent={candidate['solvent']}, concentration={candidate['concentration']}, temperature_c={candidate['temperature_c']}")
            except Exception as e:
                print(f"[ALERT] Failed to reject suggestion: {e}")
                
        # Small sleep to prevent tight loops if things are fast
        time.sleep(1.0)

    # 4. Pause campaign at the end of invocation
    try:
        client.lifecycle(campaign_id, action="pause")
        print("[EVENT] Campaign paused at the end of invocation.")
    except Exception as e:
        print(f"[ALERT] Failed to pause campaign on server: {e}")

    # 5. Print final summary
    try:
        results = client.get_results(campaign_id)
        print_final_summary(results, attempted_count, successful_count, failed_candidates)
    except Exception as e:
        print(f"[ALERT] Failed to fetch results for final summary: {e}")
        
    return campaign_id
