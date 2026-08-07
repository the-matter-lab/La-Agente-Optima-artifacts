import math
from typing import Any

def evaluate_ackley_6d(x: list[float]) -> dict[str, float]:
    """
    Evaluate the 6D Ackley function for a given point x in [0.0, 1.0]^6.
    Returns a dictionary with:
      - 'classic': the standard Ackley value
      - 'raw_response': -classic
      - 'surface_response': normalized value in [0.0, 1.0]
    """
    if len(x) != 6:
        raise ValueError(f"Expected exactly 6 dimensions, got {len(x)}")

    # Map x_i to z_i
    z = [-40.0 + 80.0 * xi for xi in x]
    d = 6.0

    sum_sq = sum(zi**2 for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)

    classic = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d)) - math.exp(sum_cos / d) + 20.0 + math.e
    raw_response = -classic

    # Normalize using fixed 6D Ackley bounds exactly
    min_raw = -22.350402387287602
    max_raw = 0.0
    surface_response = (raw_response - min_raw) / (max_raw - min_raw)

    return {
        "classic": classic,
        "raw_response": raw_response,
        "surface_response": surface_response
    }
