"""Deterministic 6D Ackley evaluator.

Search space: x_1..x_6 ∈ [0,1]
Mapping: z_i = -40 + 80 * x_i   → z_i ∈ [-40, 40]
Classic Ackley (d=6):
  classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d))
            - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))

No noise. No chemistry/experimental calls.
"""

import math

from ackley6d.search_space import DIM, PARAM_NAMES

# Pre-computed normalization constants
_RAW_RESPONSE_MIN = -22.350402387287602  # classic at z=0 → raw = 0; worst-case raw
_RAW_RESPONSE_MAX = 0.0  # best raw_response (at global optimum z=0)


def _ackley_classic(z: list[float]) -> float:
    """Classic Ackley function value for z-coordinates."""
    d = len(z)
    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)
    return (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
        - math.exp(sum_cos / d)
        + 20.0
        + math.e
    )


def evaluate(parameter_values: dict[str, float]) -> dict:
    """Evaluate the 6D Ackley surface at the given parameter point.

    Returns dict with keys:
      raw_response, surface_response, z_coords
    """
    z = [-40.0 + 80.0 * parameter_values[name] for name in PARAM_NAMES]
    classic = _ackley_classic(z)
    raw_response = -classic
    denom = _RAW_RESPONSE_MAX - _RAW_RESPONSE_MIN
    surface_response = (raw_response - _RAW_RESPONSE_MIN) / denom if denom != 0 else 0.0

    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
        "z_coords": z,
    }
