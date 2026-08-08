from __future__ import annotations

import math
from typing import Dict, Tuple

ACKLEY_CLASSIC_MIN = 0.0
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0


def evaluate_ackley_6d(point: Dict[str, float]) -> Tuple[float, float]:
    ordered = [point[f"x_{i}"] for i in range(1, 7)]
    d = len(ordered)
    z = [-40.0 + 80.0 * x for x in ordered]
    sum_sq = sum(v * v for v in z)
    sum_cos = sum(math.cos(2.0 * math.pi * v) for v in z)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(sum_cos / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
    return raw_response, surface_response
