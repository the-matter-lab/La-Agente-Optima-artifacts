from __future__ import annotations

import math
from typing import Any

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"
PARAMETER_NAMES = [f"x_{i}" for i in range(1, 7)]
DIMS = 6
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0


def parameter_key(parameter_values: dict[str, Any]) -> tuple[str, ...]:
    return tuple(f"{float(parameter_values[name]):.17g}" for name in PARAMETER_NAMES)


def evaluate_ackley(parameter_values: dict[str, float]) -> dict[str, float]:
    z_values = [-40.0 + 80.0 * float(parameter_values[name]) for name in PARAMETER_NAMES]
    squared_mean = sum(z * z for z in z_values) / DIMS
    cosine_mean = sum(math.cos(2.0 * math.pi * z) for z in z_values) / DIMS
    classic = -20.0 * math.exp(-0.2 * math.sqrt(squared_mean)) - math.exp(cosine_mean) + 20.0 + math.e
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
    return {
        "raw_response": raw_response,
        OBJECTIVE_NAME: surface_response,
    }
