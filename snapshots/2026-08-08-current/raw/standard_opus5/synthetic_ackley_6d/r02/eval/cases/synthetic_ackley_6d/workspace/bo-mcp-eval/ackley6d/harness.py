"""Campaign-agnostic evaluation harness: turns a suggestion into a result row."""

import traceback
from typing import Callable


def evaluate_candidate(
    evaluate_fn: Callable[[dict], dict],
    *,
    evaluation_index: int,
    suggestion: dict,
    objective_name: str,
) -> dict:
    """Evaluate one suggestion, never raising. Returns an artifact row."""
    params = suggestion.get("parameter_values", {})
    row = {
        "evaluation_index": evaluation_index,
        "suggestion_id": suggestion.get("suggestion_id"),
        "parameter_values": params,
        "objective_values": None,
        "status": "failed",
        "failure_reason": None,
        "raw_response": None,
    }
    try:
        out = evaluate_fn(params)
        value = float(out[objective_name])
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"non-finite {objective_name}: {value}")
        row["objective_values"] = {objective_name: value}
        row["raw_response"] = out.get("raw_response")
        row["status"] = "success"
    except Exception as exc:  # noqa: BLE001 - failures are recorded, not raised
        row["failure_reason"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc(limit=3)
    return row
