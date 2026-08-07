"""Campaign-specific evaluator: deterministic Ackley-6 surface response.

x_i in [0,1] -> z_i = -40 + 80*x_i, d = 6

    classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
    raw_response     = -classic
    surface_response = (raw_response - WORST) / (BEST - WORST)
"""

import math

from .space import DIM, coords

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "normalized_unitless"

WORST_RAW = -22.350402387287602
BEST_RAW = 0.0


def evaluate(parameter_values: dict) -> dict:
    """Return {'surface_response': float, 'raw_response': float} for one candidate."""
    z = [-40.0 + 80.0 * x for x in coords(parameter_values)]
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(zi * zi for zi in z) / DIM))
        - math.exp(sum(math.cos(2.0 * math.pi * zi) for zi in z) / DIM)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - WORST_RAW) / (BEST_RAW - WORST_RAW)
    return {"surface_response": surface_response, "raw_response": raw_response}
