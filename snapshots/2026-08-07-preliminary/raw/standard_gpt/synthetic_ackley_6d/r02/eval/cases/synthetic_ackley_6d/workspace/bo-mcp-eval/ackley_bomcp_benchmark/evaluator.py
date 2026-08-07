from __future__ import annotations

import math
from typing import Any

from .intake import OBJECTIVE_NAME
from .search_space import flatten_parameter_values, iter_parameter_values

ACKLEY_MIN_RAW_RESPONSE = -22.350402387287602
ACKLEY_MAX_RAW_RESPONSE = 0.0
ACKLEY_DIMENSION = 6


def _scaled_coordinates(parameter_values: dict[str, float]) -> list[float]:
    return [-40.0 + 80.0 * value for value in iter_parameter_values(parameter_values)]


def compute_ackley_response(parameter_values: dict[str, float]) -> dict[str, float]:
    z_values = _scaled_coordinates(parameter_values)
    sum_sq = sum(value * value for value in z_values)
    cosine_sum = sum(math.cos(2.0 * math.pi * value) for value in z_values)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / ACKLEY_DIMENSION))
        - math.exp(cosine_sum / ACKLEY_DIMENSION)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_MIN_RAW_RESPONSE) / (
        ACKLEY_MAX_RAW_RESPONSE - ACKLEY_MIN_RAW_RESPONSE
    )
    return {
        "classic": classic,
        "raw_response": raw_response,
        OBJECTIVE_NAME: surface_response,
    }


def evaluate_candidate(
    *,
    campaign_id: str,
    evaluation_index: int,
    parameter_values: dict[str, float],
    suggestion_id: str | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "evaluation_index": evaluation_index,
        "campaign_id": campaign_id,
        "suggestion_id": suggestion_id,
        "parameter_values": flatten_parameter_values(parameter_values),
        "objective_values": {},
        "status": "failed",
        "failure_reason": None,
        "raw_response": None,
        "classic": None,
    }
    try:
        response = compute_ackley_response(parameter_values)
        row["objective_values"] = {OBJECTIVE_NAME: response[OBJECTIVE_NAME]}
        row["raw_response"] = response["raw_response"]
        row["classic"] = response["classic"]
        row["status"] = "completed"
        return row
    except Exception as exc:  # pragma: no cover - defensive fallback
        row["failure_reason"] = f"{type(exc).__name__}: {exc}"
        return row
