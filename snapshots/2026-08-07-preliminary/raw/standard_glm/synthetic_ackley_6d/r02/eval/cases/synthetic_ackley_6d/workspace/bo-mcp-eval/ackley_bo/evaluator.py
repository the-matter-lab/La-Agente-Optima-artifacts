"""Deterministic Ackley evaluator in 6 normalized dimensions.

Maps normalized x_i ∈ [0,1] → z_i = -40 + 80·x_i, computes the classic
Ackley function, negates it (raw_response = -classic), then rescales to
surface_response ∈ [0,1] using the user-specified normalization constants.
"""

import math

# Normalization anchors from the task specification.
_RAW_RESPONSE_MIN = -22.350402387287602  # classic at the global minimum (≈0)
_RAW_RESPONSE_MAX = 0.0  # classic at the worst-case boundary
_D = 6


def evaluate(x: dict[str, float]) -> dict[str, float]:
    """Evaluate the Ackley surface for one candidate.

    Parameters
    ----------
    x : dict with keys x_1..x_6, each in [0, 1].

    Returns
    -------
    dict with keys ``raw_response`` and ``surface_response``.
    """
    z = [-40.0 + 80.0 * x[f"x_{i}"] for i in range(1, _D + 1)]

    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)

    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / _D))
        - math.exp(sum_cos / _D)
        + 20.0
        + math.e
    )
    raw_response = -classic

    denom = _RAW_RESPONSE_MAX - _RAW_RESPONSE_MIN
    surface_response = (raw_response - _RAW_RESPONSE_MIN) / denom if denom != 0 else 0.0

    return {"raw_response": raw_response, "surface_response": surface_response}
