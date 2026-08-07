from __future__ import annotations

import math
from typing import Mapping

ACKLEY_DIM = 6
RAW_RESPONSE_MIN = -22.350402387287602
RAW_RESPONSE_MAX = 0.0
PARAMETER_NAMES = tuple(f"x_{i}" for i in range(1, ACKLEY_DIM + 1))


def _normalized_to_ackley_axis(x: float) -> float:
    return -40.0 + 80.0 * x


def evaluate_ackley_6d(parameter_values: Mapping[str, float]) -> dict[str, float]:
    xs = [float(parameter_values[name]) for name in PARAMETER_NAMES]
    if len(xs) != ACKLEY_DIM:
        raise ValueError(f"Expected {ACKLEY_DIM} dimensions, got {len(xs)}")
    if any(x < 0.0 or x > 1.0 for x in xs):
        raise ValueError(f"Normalized Ackley coordinates must lie in [0, 1]: {xs}")

    zs = [_normalized_to_ackley_axis(x) for x in xs]
    d = float(ACKLEY_DIM)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(z * z for z in zs) / d))
        - math.exp(sum(math.cos(2.0 * math.pi * z) for z in zs) / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - RAW_RESPONSE_MIN) / (RAW_RESPONSE_MAX - RAW_RESPONSE_MIN)
    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
    }


def point_key(parameter_values: Mapping[str, float], ndigits: int = 12) -> tuple[float, ...]:
    return tuple(round(float(parameter_values[name]), ndigits) for name in PARAMETER_NAMES)
