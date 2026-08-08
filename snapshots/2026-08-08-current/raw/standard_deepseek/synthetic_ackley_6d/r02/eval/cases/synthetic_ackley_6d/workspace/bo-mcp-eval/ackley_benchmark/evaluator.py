"""Deterministic Ackley-surface evaluator for the 6-D benchmark.

Mapping (per the spec):
  z_i = -40 + 80 * x_i
  classic = -20 * exp(-0.2 * sqrt(sum(z_i^2) / d))
            - exp(sum(cos(2 * pi * z_i)) / d) + 20 + e
  raw_response = -classic
  surface_response = (raw_response - MIN_RAW) / (MAX_RAW - MIN_RAW)

where MIN_RAW = -22.350402387287602, MAX_RAW = 0.0, d = 6, e = 0 (noise-free).
"""

import math

D = 6
MIN_RAW = -22.350402387287602
MAX_RAW = 0.0
RANGE = MAX_RAW - MIN_RAW  # 22.350402387287602


def evaluate(parameter_values: dict[str, float]) -> dict:
    """Evaluate the Ackley surface for one candidate.

    Args:
        parameter_values: dict with keys x_1..x_6 in [0, 1].

    Returns:
        dict with keys: raw_response, surface_response, status.
        status is always "completed" (deterministic, noise-free).
    """
    z = [-40.0 + 80.0 * parameter_values[f"x_{i}"] for i in range(1, D + 1)]

    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)

    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / D))
        - math.exp(sum_cos / D)
        + 20.0
    )
    raw_response = -classic
    surface_response = (raw_response - MIN_RAW) / RANGE

    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
        "status": "completed",
    }