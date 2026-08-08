# direct_arylation/reporting.py

import logfire

def extract_best_result(results: list[dict]) -> dict | None:
    """Extract the best result (highest yield) from a list of results.
    
    Each result is expected to have 'parameter_values' and 'objective_values'.
    """
    best_result = None
    best_yield = -float("inf")
    
    for r in results:
        obj = r.get("objective_values", {})
        y = obj.get("yield")
        if y is not None and y > best_yield:
            best_yield = y
            best_result = r
            
    return best_result

def print_final_summary(
    results: list[dict],
    attempted_count: int,
    successful_count: int,
    failed_candidates: list[dict]
) -> None:
    """Print a concise, readable, and UI-friendly final summary of the campaign."""
    best_res = extract_best_result(results)
    
    print("\n" + "="*60)
    print(" DIRECT ARYLATION OPTIMIZATION CAMPAIGN SUMMARY")
    print("="*60)
    print(f"Attempted Evaluations:  {attempted_count}")
    print(f"Successful Evaluations: {successful_count}")
    print(f"Failed Evaluations:     {len(failed_candidates)}")
    
    if best_res:
        best_params = best_res["parameter_values"]
        best_yield = best_res["objective_values"]["yield"]
        print("\n[RESULT] BEST REACTION CONDITIONS FOUND:")
        for k, v in best_params.items():
            print(f"  - {k}: {v}")
        print(f"  - [RESULT] Best Measured Yield: {best_yield:.2f}%")
    else:
        print("\n[ALERT] No successful evaluations were recorded.")
        
    print("\n" + "-"*60)
    print(" ALL EVALUATED CANDIDATES:")
    print("-"*60)
    
    # Print successful ones
    for idx, r in enumerate(results, 1):
        params = r["parameter_values"]
        y = r["objective_values"]["yield"]
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"[{idx:02d}] SUCCESS | {param_str} -> Yield: {y:.2f}%")
        
    # Print failed ones
    for idx, f in enumerate(failed_candidates, len(results) + 1):
        params = f.get("parameter_values") or f
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        print(f"[{idx:02d}] FAILED  | {param_str}")
        
    print("="*60 + "\n")
    
    # Logfire logging
    if best_res:
        logfire.info(
            "Campaign completed. Best yield: {best_yield}% with conditions {best_params}",
            best_yield=best_res["objective_values"]["yield"],
            best_params=best_res["parameter_values"]
        )
