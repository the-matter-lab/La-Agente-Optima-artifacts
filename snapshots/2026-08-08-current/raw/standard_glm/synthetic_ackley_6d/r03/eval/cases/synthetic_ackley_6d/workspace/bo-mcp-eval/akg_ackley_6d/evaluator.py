"""Deterministic 6-D Ackley evaluator (normalized [0,1] inputs)."""

from __future__ import annotations

import math

# Pre-computed normalisation constants
_RAW_MIN = -22.350402387287602  # raw_response at the worst corner
_RAW_MAX = 0.0                  # raw_response at the global optimum (x_i = 0.5)
_SCALE = _RAW_MAX - _RAW_MIN   # 22.350402387287602


def evaluate(x_1: float, x_2: float, x_3: float,
             x_4: float, x_5: float, x_6: float) -> dict[str, float]:
    """Return {"raw_response": ..., "surface_response": ...}."""
    xs = (x_1, x_2, x_3, x_4, x_5, x_6)
    d = 6

    # Map normalised coords to the classic Ackley domain [-40, 40]
    zs = [-40.0 + 80.0 * xi for xi in xs]

    sum_sq = sum(zi * zi for zi in zs)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in zs)

    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(sum_cos / d)
        + 20.0
        + math.e
    )

    raw_response = -classic
    surface_response = (raw_response - _RAW_MIN) / _SCALE

    return {"raw_response": raw_response, "surface_response": surface_response}
