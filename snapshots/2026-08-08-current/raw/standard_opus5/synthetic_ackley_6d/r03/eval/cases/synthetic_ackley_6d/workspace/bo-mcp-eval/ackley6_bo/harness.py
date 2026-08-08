"""Campaign-agnostic candidate evaluation harness.

Runs an arbitrary evaluator over independent candidates in parallel threads and
converts exceptions/timeouts into recorded failures instead of crashing the loop.
Imports nothing campaign-specific, so continuations can reuse it unchanged.
"""

import concurrent.futures as cf
from typing import Any, Callable

Candidate = dict[str, Any]
Evaluator = Callable[[dict], dict]


def evaluate_candidates(
    candidates: list[Candidate],
    evaluator: Evaluator,
    *,
    timeout_s: float | None = None,
    max_workers: int = 6,
) -> list[dict]:
    """Evaluate candidates in parallel; return one row per candidate, in order.

    Each row: {'suggestion_id', 'parameter_values', 'status', 'values',
    'failure_reason'} with status 'success' or 'failed'.
    """
    if not candidates:
        return []
    rows: list[dict | None] = [None] * len(candidates)
    with cf.ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as pool:
        futures = {
            pool.submit(evaluator, c["parameter_values"]): i
            for i, c in enumerate(candidates)
        }
        for future, i in futures.items():
            candidate = candidates[i]
            base = {
                "suggestion_id": candidate.get("suggestion_id"),
                "parameter_values": candidate["parameter_values"],
            }
            try:
                values = future.result(timeout=timeout_s)
                rows[i] = {**base, "status": "success", "values": values, "failure_reason": None}
            except cf.TimeoutError:
                future.cancel()
                rows[i] = {
                    **base,
                    "status": "failed",
                    "values": None,
                    "failure_reason": f"evaluation timed out after {timeout_s}s",
                }
            except Exception as exc:  # noqa: BLE001 - failure is data, not a crash
                rows[i] = {
                    **base,
                    "status": "failed",
                    "values": None,
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                }
    return [row for row in rows if row is not None]
