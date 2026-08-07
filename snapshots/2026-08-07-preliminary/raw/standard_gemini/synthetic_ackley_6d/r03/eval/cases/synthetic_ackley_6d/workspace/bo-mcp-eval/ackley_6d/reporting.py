# ackley_6d/reporting.py
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

import json
import os
from typing import List, Dict, Any

def save_results_artifact(filepath: str, history: List[Dict[str, Any]]):
    """
    Saves the evaluation history to a JSON file.
    Each row contains:
      - evaluation_index
      - parameter_values (x_1..x_6)
      - objective_values (surface_response)
      - status
      - failure_reason
      - raw_response
    """
    with open(filepath, "w") as f:
        json.dump(history, f, indent=2)

def print_final_report(campaign_id: str, history: List[Dict[str, Any]]):
    """
    Prints the final report of the campaign.
    """
    successful_evals = [h for h in history if h["status"] == "success"]
    attempted_evals = len(history)
    successful_count = len(successful_evals)
    
    print("\n" + "="*80)
    print("FINAL CAMPAIGN REPORT")
    print("="*80)
    print(f"Campaign ID: {campaign_id}")
    print(f"Attempted Evaluations: {attempted_evals}")
    print(f"Successful Evaluations: {successful_count}")
    print(f"Failed Evaluations: {attempted_evals - successful_count}")
    
    if successful_evals:
        # Find the best candidate (maximizing surface_response)
        best_candidate = max(successful_evals, key=lambda x: x["objective_values"]["surface_response"])
        print("\nBEST CANDIDATE FOUND:")
        print(f"  Surface Response (Normalized): {best_candidate['objective_values']['surface_response']:.6f}")
        print(f"  Raw Response: {best_candidate['raw_response']:.6f}")
        print("  Normalized Coordinates:")
        for k, v in sorted(best_candidate["parameter_values"].items()):
            print(f"    {k}: {v:.6f}")
    else:
        print("\n[ALERT] No successful evaluations recorded.")
        
    print("\nEVALUATION HISTORY TABLE:")
    print(f"{'Index':<6} | {'x_1':<8} | {'x_2':<8} | {'x_3':<8} | {'x_4':<8} | {'x_5':<8} | {'x_6':<8} | {'Surface Resp':<12} | {'Status':<8}")
    print("-" * 100)
    for h in history:
        idx = h["evaluation_index"]
        p = h["parameter_values"]
        obj = h["objective_values"].get("surface_response", float('nan')) if h["status"] == "success" else float('nan')
        status = h["status"]
        
        p_str = " | ".join(f"{p.get(f'x_{i}', float('nan')):.4f}" for i in range(1, 7))
        obj_str = f"{obj:.6f}" if not math_isnan(obj) else "N/A"
        print(f"{idx:<6} | {p_str} | {obj_str:<12} | {status:<8}")
        
    print("="*80)
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}")
    print("="*80)

def math_isnan(val: float) -> bool:
    try:
        import math
        return math.isnan(val)
    except:
        return False
