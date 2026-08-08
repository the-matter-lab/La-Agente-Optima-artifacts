"""Campaign-agnostic evaluation harness: run an evaluator over candidates."""

from typing import Any, Callable


def evaluate_candidates(
    candidates: list[dict[str, Any]],
    evaluator: Callable[[dict[str, float]], dict[str, float]],
    start_index: int,
) -> list[dict[str, Any]]:
    """Evaluate candidates, capturing per-candidate failures.

    Each row: evaluation_index, suggestion_id, parameter_values, values,
    status ('success'|'failed'), failure_reason.
    """
    rows = []
    for offset, cand in enumerate(candidates):
        row = {
            "evaluation_index": start_index + offset,
            "suggestion_id": cand.get("suggestion_id"),
            "parameter_values": cand["parameter_values"],
            "values": None,
            "status": "success",
            "failure_reason": None,
        }
        try:
            row["values"] = evaluator(cand["parameter_values"])
        except Exception as exc:  # noqa: BLE001 - record and continue in budget
            row["status"] = "failed"
            row["failure_reason"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return rows
