# Objective extraction and reporting module for direct arylation campaign
import logfire

def extract_objective(evaluation_result: dict) -> float:
    """Extract the yield objective value from the evaluation result."""
    return float(evaluation_result["yield"])

def report_result(candidate: dict, yield_val: float, status: str):
    """Print a standardized result line for the main agent's monitor."""
    if status == "success":
        print(f"[RESULT] Candidate: {candidate} -> yield: {yield_val}% (status: {status})", flush=True)
    else:
        print(f"[RESULT] Candidate: {candidate} -> yield: None (status: {status})", flush=True)
