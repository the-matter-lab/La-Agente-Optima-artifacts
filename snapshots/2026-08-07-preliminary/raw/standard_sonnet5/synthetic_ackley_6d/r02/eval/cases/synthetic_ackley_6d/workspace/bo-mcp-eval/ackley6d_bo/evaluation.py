"""Campaign-agnostic candidate-evaluation harness.

Takes an arbitrary ``evaluate_fn(parameter_values) -> dict`` and never raises:
failures are captured and reported as a status record so a campaign loop can
record them and keep going within the same budget. No campaign-specific
imports here so this module is reusable unchanged by other campaigns.
"""

from typing import Callable


def run_candidate(evaluate_fn: Callable[[dict], dict], parameter_values: dict) -> dict:
    """Evaluate one candidate. Returns {status, outputs, failure_reason}."""
    try:
        outputs = evaluate_fn(parameter_values)
        return {"status": "success", "outputs": outputs, "failure_reason": None}
    except Exception as exc:  # noqa: BLE001 - deliberately broad: never crash the loop
        return {
            "status": "failed",
            "outputs": None,
            "failure_reason": f"{type(exc).__name__}: {exc}",
        }
