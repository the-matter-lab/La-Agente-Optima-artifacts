import logging
from .evaluation import load_attempts

logger = logging.getLogger(__name__)


def report_results() -> None:
    """Report all evaluated candidates and their statuses/objective values."""
    attempts = load_attempts()
    if not attempts:
        print("[ALERT] No attempts found to report.")
        return

    print("\n" + "=" * 60)
    print("CAMPAIGN EVALUATION REPORT")
    print("=" * 60)
    print(f"Total attempts: {len(attempts)}")

    successes = [a for a in attempts if a["status"] == "success"]
    failures = [a for a in attempts if a["status"] == "failed"]

    print(f"Successful evaluations: {len(successes)}")
    print(f"Failed evaluations: {len(failures)}")
    print("-" * 60)

    best_yield = -1.0
    best_candidate = None

    for i, attempt in enumerate(attempts, 1):
        params = attempt["parameter_values"]
        status = attempt["status"]
        if status == "success":
            val = attempt["objective_values"]["yield"]
            print(f"[{i:02d}] SUCCESS: {params} -> yield: {val}%")
            if val > best_yield:
                best_yield = val
                best_candidate = params
        else:
            err = attempt.get("error_message", "Unknown error")
            print(f"[{i:02d}] FAILED : {params} -> Error: {err}")

    print("-" * 60)
    if best_candidate:
        print("[RESULT] Best Candidate Found:")
        print(f"  Parameters: {best_candidate}")
        print(f"  Max Yield : {best_yield}%")
    else:
        print("[ALERT] No successful evaluations to determine the best candidate.")
    print("=" * 60 + "\n")
