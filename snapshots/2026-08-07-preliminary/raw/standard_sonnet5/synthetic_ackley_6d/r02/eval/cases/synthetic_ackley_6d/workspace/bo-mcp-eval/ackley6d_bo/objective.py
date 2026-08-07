"""Deterministic synthetic Ackley-6D objective. No chemistry/experimental evaluator.

Mapping per candidate x_i in [0, 1] -> z_i = -40 + 80 * x_i, d = 6:
    classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
    raw_response = -classic
    surface_response = (raw_response - WORST_RAW) / (BEST_RAW - WORST_RAW)
"""

import math

from .search_space import PARAM_NAMES

D = 6
BEST_RAW = 0.0
WORST_RAW = -22.350402387287602


def evaluate(parameter_values: dict) -> dict:
    """Compute {raw_response, surface_response} for one candidate. Raises on bad input."""
    z = [-40.0 + 80.0 * float(parameter_values[name]) for name in PARAM_NAMES]
    sphere_term = math.sqrt(sum(v * v for v in z) / D)
    cosine_term = sum(math.cos(2.0 * math.pi * v) for v in z) / D
    classic = -20.0 * math.exp(-0.2 * sphere_term) - math.exp(cosine_term) + 20.0 + math.e
    raw_response = -classic
    surface_response = (raw_response - WORST_RAW) / (BEST_RAW - WORST_RAW)
    return {"raw_response": raw_response, "surface_response": surface_response}
