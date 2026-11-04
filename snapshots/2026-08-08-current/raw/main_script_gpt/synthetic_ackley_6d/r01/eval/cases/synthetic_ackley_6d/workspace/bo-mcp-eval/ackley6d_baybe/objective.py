from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0
PARAMETER_NAMES = [f"x_{i}" for i in range(1, 7)]


@dataclass(frozen=True)
class AckleyEvaluation:
    parameter_values: dict[str, float]
    raw_response: float
    surface_response: float


def ackley_surface(parameter_values: Mapping[str, float]) -> AckleyEvaluation:
    z_values = [-40.0 + 80.0 * float(parameter_values[name]) for name in PARAMETER_NAMES]
    d = float(len(z_values))
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(z * z for z in z_values) / d))
        - math.exp(sum(math.cos(2.0 * math.pi * z) for z in z_values) / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
    return AckleyEvaluation(
        parameter_values={name: float(parameter_values[name]) for name in PARAMETER_NAMES},
        raw_response=raw_response,
        surface_response=surface_response,
    )


def parameter_key(parameter_values: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(format(float(parameter_values[name]), ".17g") for name in PARAMETER_NAMES)
