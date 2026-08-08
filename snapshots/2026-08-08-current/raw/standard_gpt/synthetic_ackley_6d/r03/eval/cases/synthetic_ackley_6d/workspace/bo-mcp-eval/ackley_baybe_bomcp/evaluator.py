from __future__ import annotations

import math
from typing import Mapping

from .search_space import DIMENSION, PARAMETER_NAMES, ordered_parameter_values

RAW_RESPONSE_FLOOR = -22.350402387287602
RAW_RESPONSE_CEILING = 0.0


def evaluate_ackley(parameter_values: Mapping[str, float]) -> dict[str, object]:
    ordered = ordered_parameter_values(parameter_values)
    normalized = [ordered[name] for name in PARAMETER_NAMES]
    for name, value in ordered.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must lie on [0.0, 1.0]; received {value!r}")

    transformed = [-40.0 + 80.0 * value for value in normalized]
    sum_sq = sum(value * value for value in transformed)
    sum_cos = sum(math.cos(2.0 * math.pi * value) for value in transformed)

    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / DIMENSION))
        - math.exp(sum_cos / DIMENSION)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - RAW_RESPONSE_FLOOR) / (RAW_RESPONSE_CEILING - RAW_RESPONSE_FLOOR)

    return {
        "parameter_values": ordered,
        "objective_values": {"surface_response": surface_response},
        "raw_response": raw_response,
    }
