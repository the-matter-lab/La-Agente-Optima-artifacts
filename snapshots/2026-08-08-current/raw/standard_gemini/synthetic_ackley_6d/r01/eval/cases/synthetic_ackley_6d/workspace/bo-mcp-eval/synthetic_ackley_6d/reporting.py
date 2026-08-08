import os
import json
from typing import Any, Dict, List, Optional

def get_artifact_path(artifact_dir: str = "artifacts") -> str:
    """
    Returns the path to the results artifact file.
    """
    os.makedirs(artifact_dir, exist_ok=True)
    return os.path.join(artifact_dir, "results_artifact.json")

def load_results_artifact(artifact_dir: str = "artifacts") -> List[Dict[str, Any]]:
    """
    Loads the results artifact from disk if it exists.
    """
    path = get_artifact_path(artifact_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_results_artifact(results: List[Dict[str, Any]], artifact_dir: str = "artifacts") -> None:
    """
    Saves the full list of results to the results artifact file.
    """
    path = get_artifact_path(artifact_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

def append_to_results_artifact(
    evaluation_index: int,
    parameter_values: Dict[str, float],
    objective_values: Dict[str, float],
    status: str,
    failure_reason: Optional[str] = None,
    raw_response: Optional[float] = None,
    artifact_dir: str = "artifacts"
) -> List[Dict[str, Any]]:
    """
    Appends a single evaluation result to the results artifact.
    """
    results = load_results_artifact(artifact_dir)
    
    # Check if this evaluation_index already exists to avoid duplicates on resume
    for r in results:
        if r.get("evaluation_index") == evaluation_index:
            # Update it
            r["parameter_values"] = parameter_values
            r["objective_values"] = objective_values
            r["status"] = status
            r["failure_reason"] = failure_reason
            r["raw_response"] = raw_response
            save_results_artifact(results, artifact_dir)
            return results
            
    new_row = {
        "evaluation_index": evaluation_index,
        "parameter_values": parameter_values,
        "objective_values": objective_values,
        "status": status,
        "failure_reason": failure_reason,
        "raw_response": raw_response
    }
    results.append(new_row)
    save_results_artifact(results, artifact_dir)
    return results

def generate_final_report(artifact_dir: str = "artifacts") -> None:
    """
    Generates and prints the final report based on the results artifact.
    """
    results = load_results_artifact(artifact_dir)
    if not results:
        print("[ALERT] No results found in artifact to report.")
        return
        
    successful_evals = 0
    attempted_evals = len(results)
    
    best_surface_response = -float("inf")
    best_raw_response = -float("inf")
    best_coords = None
    
    table_rows = []
    
    for r in results:
        idx = r.get("evaluation_index")
        params = r.get("parameter_values", {})
        objs = r.get("objective_values", {})
        status = r.get("status")
        fail_reason = r.get("failure_reason")
        raw_resp = r.get("raw_response")
        
        surf_resp = objs.get("surface_response")
        
        if status == "success" and surf_resp is not None:
            successful_evals += 1
            if surf_resp > best_surface_response:
                best_surface_response = surf_resp
                best_raw_response = raw_resp if raw_resp is not None else -float("inf")
                best_coords = params
                
        # Format coordinates for table
        coords_str = ", ".join(f"{k}:{v:.4f}" for k, v in sorted(params.items()))
        surf_str = f"{surf_resp:.6f}" if surf_resp is not None else "N/A"
        raw_str = f"{raw_resp:.6f}" if raw_resp is not None else "N/A"
        
        table_rows.append(
            f"| {idx:<5} | {status:<8} | {surf_str:<16} | {raw_str:<12} | {coords_str} |"
        )
        
    print("\n" + "="*80)
    print("CAMPAIGN OPTIMIZATION REPORT")
    print("="*80)
    print(f"Attempted Evaluations:  {attempted_evals}")
    print(f"Successful Evaluations: {successful_evals}")
    print(f"Failed Evaluations:     {attempted_evals - successful_evals}")
    print("-"*80)
    
    if best_coords is not None:
        print("BEST CANDIDATE FOUND:")
        print(f"  Best Surface Response (normalized): {best_surface_response:.8f}")
        print(f"  Best Raw Response:                  {best_raw_response:.8f}")
        print("  Best Coordinates:")
        for k, v in sorted(best_coords.items()):
            print(f"    {k}: {v:.8f}")
    else:
        print("No successful evaluations found.")
        
    print("-"*80)
    print("EVALUATION HISTORY TABLE:")
    print("| Index | Status   | Surface Response | Raw Response | Coordinates |")
    print("|-------|----------|------------------|--------------|-------------|")
    for row in table_rows:
        print(row)
    print("="*80 + "\n")
