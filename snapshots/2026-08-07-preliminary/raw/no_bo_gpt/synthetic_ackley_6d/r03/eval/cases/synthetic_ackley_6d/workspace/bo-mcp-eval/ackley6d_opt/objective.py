from __future__ import annotations

import math
from typing import Dict, Tuple

ACKLEY_LOWER = -22.350402387287602
ACKLEY_UPPER = 0.0
DIMENSION = 6
PARAMETER_NAMES = tuple(f"x_{i}" for i in range(1, DIMENSION + 1))


def normalized_to_z(x: float) -> float:
    return -40.0 + 80.0 * x


def evaluate_ackley(parameter_values: Dict[str, float]) -> Tuple[float, float]:
    xs = [parameter_values[name] for name in PARAMETER_NAMES]
    zs = [normalized_to_z(x) for x in xs]
    d = len(zs)
    sum_sq = sum(z * z for z in zs)
    sum_cos = sum(math.cos(2.0 * math.pi * z) for z in zs)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(sum_cos / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_LOWER) / (ACKLEY_UPPER - ACKLEY_LOWER)
    return raw_response, surface_response
