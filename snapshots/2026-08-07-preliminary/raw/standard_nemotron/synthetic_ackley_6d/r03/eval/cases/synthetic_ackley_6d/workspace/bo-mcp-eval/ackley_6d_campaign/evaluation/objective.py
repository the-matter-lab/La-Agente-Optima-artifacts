"""Deterministic Ackley objective function for 6D optimization.

The function maps x_i in [0, 1] to z_i = -40 + 80*x_i, then computes:
classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))

The global maximum of surface_response is 1.0 at x_i = 0.5 (z_i = 0).

Cache-buster nonce: 87fe1294-416b-4ab4-8491-0d8cb2c43c23
"""

import math
from typing import Any

# Constants from the specification
D = 6
Z_SCALE = 80.0
Z_OFFSET = -40.0
CLASSIC_MIN = -22.350402387287602  # raw_response at worst point
CLASSIC_MAX = 0.0  # raw_response at global optimum (z_i = 0)


def ackley_classic(z: list[float]) -> float:
    """Compute classic Ackley function value for given z coordinates."""
    d = len(z)
    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2.0 * math.pi * zi) for zi in z)

    term1 = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
    term2 = -math.exp(sum_cos / d)
    return term1 + term2 + 20.0 + math.e


def evaluate_ackley(x: dict[str, float]) -> dict[str, float]:
    """Evaluate the 6D Ackley function at point x.

    Args:
        x: Dictionary with keys x_1 through x_6, values in [0, 1]

    Returns:
        Dictionary with 'raw_response' and 'surface_response'
    """
    # Extract and validate parameters
    z = []
    for i in range(1, 7):
        xi = x.get(f"x_{i}")
        if xi is None:
            raise ValueError(f"Missing parameter x_{i}")
        if not (0.0 <= xi <= 1.0):
            raise ValueError(f"Parameter x_{i} = {xi} out of bounds [0, 1]")
        zi = Z_OFFSET + Z_SCALE * xi
        z.append(zi)

    # Compute classic Ackley
    classic = ackley_classic(z)
    raw_response = -classic

    # Normalize to [0, 1] where 1 is the global maximum
    surface_response = (raw_response - CLASSIC_MIN) / (CLASSIC_MAX - CLASSIC_MIN)

    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
    }


def get_optimum() -> dict[str, Any]:
    """Return the known global optimum."""
    return {
        "x": {f"x_{i}": 0.5 for i in range(1, 7)},
        "z": [0.0] * 6,
        "raw_response": CLASSIC_MAX,
        "surface_response": 1.0,
    }