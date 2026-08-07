from __future__ import annotations

import math
from typing import Any

from .search_space import (
    DIMENSIONS,
    OBJECTIVE_NAME,
    PARAMETER_NAMES,
    RAW_RESPONSE_MIN,
    normalize_parameter_values,
)


def evaluate_candidate(
    parameter_values: dict[str, Any],
    *,
    evaluation_index: int,
    suggestion_id: str,
) -> dict[str, Any]:
    try:
        normalized = normalize_parameter_values(parameter_values)
        z_values = [-40.0 + 80.0 * normalized[name] for name in PARAMETER_NAMES]
        mean_square = sum(value * value for value in z_values) / DIMENSIONS
        mean_cosine = sum(math.cos(2.0 * math.pi * value) for value in z_values) / DIMENSIONS
        classic = -20.0 * math.exp(-0.2 * math.sqrt(mean_square)) - math.exp(mean_cosine) + 20.0 + math.e
        raw_response = -classic
        surface_response = (raw_response - RAW_RESPONSE_MIN) / (0.0 - RAW_RESPONSE_MIN)
        return {
            "evaluation_index": evaluation_index,
            "parameter_values": normalized,
            "objective_values": {OBJECTIVE_NAME: surface_response},
            "status": "completed",
            "failure_reason": None,
            "raw_response": raw_response,
            "suggestion_id": suggestion_id,
        }
    except Exception as exc:
        safe_values = {
            name: float(parameter_values[name])
            for name in PARAMETER_NAMES
            if name in parameter_values
        }
        return {
            "evaluation_index": evaluation_index,
            "parameter_values": safe_values,
            "objective_values": {},
            "status": "failed",
            "failure_reason": f"{type(exc).__name__}: {exc}",
            "raw_response": None,
            "suggestion_id": suggestion_id,
        }


def build_result_payload(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("status") != "completed":
        raise ValueError("Only completed evaluations can be submitted to BO-MCP.")
    raw_response = float(record["raw_response"])
    return {
        "suggestion_id": str(record["suggestion_id"]),
        "parameter_values": dict(record["parameter_values"]),
        "objective_values": dict(record["objective_values"]),
        "metadata": {
            "notes": (
                "Deterministic Ackley 6D synthetic benchmark "
                f"raw_response={raw_response:.16f}"
            )
        },
    }
