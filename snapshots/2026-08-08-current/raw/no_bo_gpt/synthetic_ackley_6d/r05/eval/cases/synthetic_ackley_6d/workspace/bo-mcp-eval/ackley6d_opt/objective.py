from __future__ import annotations

import math
from typing import Dict

DIMS = 6
RAW_MIN = -22.350402387287602
RAW_MAX = 0.0
PARAMETER_NAMES = [f"x_{i}" for i in range(1, DIMS + 1)]


def normalized_to_ackley_z(x: float) -> float:
    return -40.0 + 80.0 * x


def evaluate_surface(parameter_values: Dict[str, float]) -> Dict[str, float]:
    xs = [float(parameter_values[name]) for name in PARAMETER_NAMES]
    zs = [normalized_to_ackley_z(x) for x in xs]
    mean_sq = sum(z * z for z in zs) / DIMS
    mean_cos = sum(math.cos(2.0 * math.pi * z) for z in zs) / DIMS
    classic = -20.0 * math.exp(-0.2 * math.sqrt(mean_sq)) - math.exp(mean_cos) + 20.0 + math.e
    raw_response = -classic
    surface_response = (raw_response - RAW_MIN) / (RAW_MAX - RAW_MIN)
    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
    }
