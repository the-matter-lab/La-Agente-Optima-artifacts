"""Deterministic synthetic objective: negated 6D Ackley, normalized.

No chemistry/experimental evaluator is involved. Nonce: f42213a0-34a7-4c2a-bbef-8b4700e0fb91
"""

import math

from .space import DIM, PARAM_NAMES

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "normalized_unitless"

RAW_MIN = -22.350402387287602
RAW_MAX = 0.0


def evaluate(params: dict[str, float]) -> dict[str, float]:
    """Map x_i -> z_i = -40 + 80*x_i and return raw/normalized responses."""
    z = [-40.0 + 80.0 * float(params[name]) for name in PARAM_NAMES]
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(v * v for v in z) / DIM))
        - math.exp(sum(math.cos(2.0 * math.pi * v) for v in z) / DIM)
        + 20.0
        + math.e
    )
    raw_response = -classic
    return {
        "raw_response": raw_response,
        OBJECTIVE_NAME: (raw_response - RAW_MIN) / (RAW_MAX - RAW_MIN),
    }
