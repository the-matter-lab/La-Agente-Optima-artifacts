"""Deterministic 6D Ackley evaluator.

Mapping:  z_i = -40 + 80 * x_i   (x_i in [0,1] → z_i in [-40, 40])
Classic:  -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
"""

import math
from typing import Any

from .search_space import DIM

# Pre-computed normalization constants
_RAW_AT_ORIGIN = 0.0  # raw_response at x_i = 0.5 (z_i = 0) → classic = 0 → raw = 0
_RAW_WORST = -22.350402387287602  # raw_response at the worst point
_NORM_RANGE = 0.0 - _RAW_WORST  # = 22.350402387287602


def _classic_ackley(z: list[float]) -> float:
    """Standard Ackley function value for z-coordinates."""
    d = len(z)
    sum_sq = sum(v * v for v in z)
    sum_cos = sum(math.cos(2.0 * math.pi * v) for v in z)
    return (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(sum_cos / d)
        + 20.0
        + math.e
    )


def evaluate(parameter_values: dict[str, Any]) -> dict[str, float]:
    """Evaluate the 6D Ackley surface at normalised coordinates.

    Returns dict with keys ``raw_response`` and ``surface_response``.
    """
    z = [-40.0 + 80.0 * float(parameter_values[f"x_{i}"]) for i in range(1, DIM + 1)]
    classic = _classic_ackley(z)
    raw_response = -classic
    surface_response = (raw_response - _RAW_WORST) / _NORM_RANGE
    return {"raw_response": raw_response, "surface_response": surface_response}
