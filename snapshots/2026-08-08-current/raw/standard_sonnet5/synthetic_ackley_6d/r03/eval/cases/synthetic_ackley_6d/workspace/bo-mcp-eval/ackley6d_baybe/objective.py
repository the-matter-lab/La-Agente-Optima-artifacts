"""Deterministic 6D Ackley synthetic objective. No noise, no evaluator calls.

Mapping: x_i in [0, 1] -> z_i = -40 + 80 * x_i (classic Ackley domain [-40, 40]).
classic  = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response     = -classic
surface_response = (raw_response - WORST_RAW_RESPONSE) / (BEST_RAW_RESPONSE - WORST_RAW_RESPONSE)

WORST_RAW_RESPONSE is the exact raw_response at a domain corner (all
z_i = +/-40), BEST_RAW_RESPONSE is the raw_response at the global optimum
z = 0 (classic Ackley value 0). No other rescaling/negation is applied.
"""
import math

from .search_space import DIMENSIONS, PARAMETER_NAMES

OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"
WORST_RAW_RESPONSE = -22.350402387287602
BEST_RAW_RESPONSE = 0.0


def _to_ackley_coords(parameter_values: dict) -> list[float]:
    return [-40.0 + 80.0 * float(parameter_values[name]) for name in PARAMETER_NAMES]


def classic_ackley(z: list[float]) -> float:
    d = DIMENSIONS
    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)
    term1 = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
    term2 = -math.exp(sum_cos / d)
    return term1 + term2 + 20.0 + math.e


def compute_surface_response(parameter_values: dict) -> tuple[float, float]:
    """Return (raw_response, surface_response) for one candidate point."""
    z = _to_ackley_coords(parameter_values)
    classic = classic_ackley(z)
    raw_response = -classic
    span = BEST_RAW_RESPONSE - WORST_RAW_RESPONSE
    surface_response = (raw_response - WORST_RAW_RESPONSE) / span
    return raw_response, surface_response
