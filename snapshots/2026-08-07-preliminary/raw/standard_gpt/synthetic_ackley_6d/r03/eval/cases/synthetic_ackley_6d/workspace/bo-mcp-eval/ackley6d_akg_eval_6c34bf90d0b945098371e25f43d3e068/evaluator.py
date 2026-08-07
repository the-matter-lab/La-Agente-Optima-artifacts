from __future__ import annotations

import math
from typing import Mapping

from .search_space import ACKLEY_RAW_MIN, DIMENSION, OBJECTIVE_NAME, PARAMETER_NAMES


def parameter_key(parameter_values: Mapping[str, float]) -> tuple[float, ...]:
    return tuple(round(float(parameter_values[name]), 12) for name in PARAMETER_NAMES)


def normalized_to_ackley_coordinates(parameter_values: Mapping[str, float]) -> list[float]:
    return [-40.0 + 80.0 * float(parameter_values[name]) for name in PARAMETER_NAMES]


def evaluate_ackley(parameter_values: Mapping[str, float]) -> dict[str, float]:
    z_values = normalized_to_ackley_coordinates(parameter_values)
    d = DIMENSION
    sum_sq = sum(value * value for value in z_values)
    cosine_term = sum(math.cos(2.0 * math.pi * value) for value in z_values)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(cosine_term / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_RAW_MIN) / (0.0 - ACKLEY_RAW_MIN)
    return {
        OBJECTIVE_NAME: surface_response,
        "raw_response": raw_response,
        "classic": classic,
    }
