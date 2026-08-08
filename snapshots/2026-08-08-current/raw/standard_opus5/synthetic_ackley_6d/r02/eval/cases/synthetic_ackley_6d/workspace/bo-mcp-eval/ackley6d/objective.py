"""Ackley synthetic surface (6D), noiseless."""

import math

from .space import DIM, PARAM_NAMES

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"
RAW_MIN = -22.350402387287602
RAW_MAX = 0.0


def evaluate(parameter_values: dict) -> dict:
    """Return {'surface_response': ..., 'raw_response': ...} for one candidate."""
    z = [-40.0 + 80.0 * float(parameter_values[n]) for n in PARAM_NAMES]
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(v * v for v in z) / DIM))
        - math.exp(sum(math.cos(2.0 * math.pi * v) for v in z) / DIM)
        + 20.0
        + math.e
    )
    raw = -classic
    return {
        "surface_response": (raw - RAW_MIN) / (RAW_MAX - RAW_MIN),
        "raw_response": raw,
    }
