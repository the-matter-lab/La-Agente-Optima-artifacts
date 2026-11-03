from __future__ import annotations

import math
from typing import Dict, Iterable, Tuple

ACKLEY_D = 6
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0


def validate_params(params: Dict[str, float]) -> None:
    expected = {f"x_{i}" for i in range(1, ACKLEY_D + 1)}
    if set(params) != expected:
        raise ValueError(f"Expected parameters {sorted(expected)}, got {sorted(params)}")
    for key, value in params.items():
        if not (0.0 <= float(value) <= 1.0):
            raise ValueError(f"{key}={value} is outside [0, 1]")


def normalized_to_ackley_coords(values: Iterable[float]) -> Tuple[float, ...]:
    return tuple(-40.0 + 80.0 * float(v) for v in values)


def evaluate_surface(params: Dict[str, float]) -> Dict[str, float]:
    validate_params(params)
    x_values = [float(params[f"x_{i}"]) for i in range(1, ACKLEY_D + 1)]
    z_values = normalized_to_ackley_coords(x_values)
    d = float(ACKLEY_D)
    sum_sq = sum(z * z for z in z_values)
    cos_term = sum(math.cos(2.0 * math.pi * z) for z in z_values)
    classic = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d)) - math.exp(cos_term / d) + 20.0 + math.e
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
    }
