from __future__ import annotations

import math
from typing import Dict, List, Tuple

ACKLEY_CLASSIC_MIN = 0.0
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0


def normalized_to_z(x: List[float]) -> List[float]:
    return [-40.0 + 80.0 * float(v) for v in x]


def ackley_raw_response(x: List[float]) -> Tuple[float, List[float], float]:
    z = normalized_to_z(x)
    d = len(z)
    sum_sq = sum(v * v for v in z)
    cos_sum = sum(math.cos(2.0 * math.pi * v) for v in z)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(cos_sum / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    return raw_response, z, classic


def surface_response(x: List[float]) -> Dict[str, float | List[float]]:
    raw_response, z, classic = ackley_raw_response(x)
    normalized = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
    return {
        "raw_response": raw_response,
        "surface_response": normalized,
        "classic": classic,
        "z": z,
    }
