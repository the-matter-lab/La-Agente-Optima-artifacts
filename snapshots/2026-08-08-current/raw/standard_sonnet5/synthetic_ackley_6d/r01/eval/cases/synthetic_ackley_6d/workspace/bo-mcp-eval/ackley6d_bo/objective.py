"""Synthetic 6D Ackley objective (no chemistry, no external evaluator).

classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response = -classic
surface_response = (raw_response - RAW_MIN) / (RAW_MAX - RAW_MIN)

with d=6, z_i = -40 + 80*x_i, x_i in [0,1]. Deterministic, no noise.
"""
import math

from .search_space import N_DIMS, PARAM_NAMES

D = N_DIMS
RAW_MIN = -22.350402387287602  # raw_response at the worst point
RAW_MAX = 0.0  # raw_response at the global optimum (z_i = 0 for all i)

CACHE_BUSTER_NONCE = "f62806c2-a95a-4a49-80eb-993714a47ac6"


def _to_z(x_i: float) -> float:
    return -40.0 + 80.0 * x_i


def classic_ackley(params: dict) -> float:
    zs = [_to_z(params[name]) for name in PARAM_NAMES]
    sum_sq = sum(z * z for z in zs)
    sum_cos = sum(math.cos(2.0 * math.pi * z) for z in zs)
    term1 = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / D))
    term2 = -math.exp(sum_cos / D)
    return term1 + term2 + 20.0 + math.e


def evaluate_candidate(params: dict) -> dict:
    """Evaluate one candidate. Never raises; returns a status dict.

    On success: {"status": "success", "raw_response": float,
                 "surface_response": float}
    On failure: {"status": "failed", "failure_reason": str}
    """
    try:
        for name in PARAM_NAMES:
            v = float(params[name])
            if not (0.0 <= v <= 1.0) or math.isnan(v):
                raise ValueError(f"{name}={v} out of bounds [0,1]")
        classic = classic_ackley(params)
        raw_response = -classic
        surface_response = (raw_response - RAW_MIN) / (RAW_MAX - RAW_MIN)
        if not math.isfinite(surface_response):
            raise ValueError("non-finite surface_response")
        return {
            "status": "success",
            "raw_response": raw_response,
            "surface_response": surface_response,
        }
    except Exception as exc:  # noqa: BLE001 - synthetic eval must never crash the loop
        return {"status": "failed", "failure_reason": f"{type(exc).__name__}: {exc}"}
