from __future__ import annotations

from robochemflex_yield_bo.objectives import extract_yield_percent, green_score


def objective_values(yield_percent: float) -> dict[str, float]:
    return {"yield_percent": float(yield_percent)}
