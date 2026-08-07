"""Deterministic 6D Ackley synthetic evaluator.

Maps x_i ∈ [0,1] → z_i ∈ [-40, 40], evaluates the classic Ackley
function, then normalizes to ``surface_response`` ∈ [0, 1] where 1.0
is the global optimum at x_i = 0.5 (z_i = 0).
"""

import math

# ── constants ──────────────────────────────────────────────────────────
_D = 6
_A = 20.0
_B = 0.2
_C = 2.0 * math.pi
_E = math.e

# Normalisation pivot: raw_response at the worst point in the domain
# maps to 0.0; raw_response at the optimum maps to 1.0.
_RAW_MIN = -22.350402387287602  # worst-case raw_response in [-40,40]^6
_RAW_OPT = 0.0  # raw_response at z_i = 0 (global optimum)


def evaluate(candidate: dict[str, float]) -> dict:
    """Evaluate one candidate and return a result row dict.

    Parameters
    ----------
    candidate : dict[str, float]
        Keys ``x_1`` … ``x_6`` with values in [0, 1].

    Returns
    -------
    dict
        ``parameter_values``, ``objective_values``, ``raw_response``,
        ``status``, ``failure_reason`` (empty string on success).
    """
    try:
        z = [_to_z(candidate[f"x_{i}"]) for i in range(1, _D + 1)]
        classic = _ackley_classic(z)
        raw = -classic
        surface = _normalize(raw)
        return {
            "parameter_values": dict(candidate),
            "objective_values": {"surface_response": surface},
            "raw_response": raw,
            "status": "success",
            "failure_reason": "",
        }
    except Exception as exc:
        return {
            "parameter_values": dict(candidate),
            "objective_values": {},
            "raw_response": None,
            "status": "failed",
            "failure_reason": str(exc),
        }


# ── helpers ────────────────────────────────────────────────────────────


def _to_z(x: float) -> float:
    """Map normalised coordinate to the Ackley domain."""
    return -40.0 + 80.0 * x


def _ackley_classic(z: list[float]) -> float:
    """Classic Ackley function (minimisation form)."""
    sum_sq = sum(v * v for v in z)
    sum_cos = sum(math.cos(_C * v) for v in z)
    term1 = -_A * math.exp(-_B * math.sqrt(sum_sq / _D))
    term2 = -math.exp(sum_cos / _D)
    return term1 + term2 + _A + _E


def _normalize(raw: float) -> float:
    """Linearly map raw_response → surface_response ∈ [0, 1]."""
    return (raw - _RAW_MIN) / (_RAW_OPT - _RAW_MIN)