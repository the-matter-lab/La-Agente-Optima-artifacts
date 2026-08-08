"""Candidate evaluation for Ackley 6D synthetic benchmark.

Deterministic evaluation of the Ackley function with the specified mapping:
- x_i in [0,1] -> z_i = -40 + 80*x_i
- classic = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
- raw_response = -classic
- surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
"""

import math
from typing import Any

# Constants from the specification
RAW_RESPONSE_MIN = -22.350402387287602  # minimum of raw_response (when classic is maximized)
RAW_RESPONSE_MAX = 0.0  # maximum of raw_response (when classic = 0 at origin)
SURFACE_DENOMINATOR = RAW_RESPONSE_MAX - RAW_RESPONSE_MIN  # = 22.350402387287602


def ackley_classic(z: list[float]) -> float:
    """Compute classic Ackley function value at z (unnormalized coordinates)."""
    d = len(z)
    sum_sq = sum(zi * zi for zi in z)
    sum_cos = sum(math.cos(2 * math.pi * zi) for zi in z)
    term1 = -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / d))
    term2 = -math.exp(sum_cos / d)
    return term1 + term2 + 20.0 + math.e


def evaluate_ackley(x: dict[str, float]) -> dict[str, Any]:
    """Evaluate the Ackley function at normalized coordinates x_1..x_6.

    Args:
        x: Dict with keys x_1 through x_6, values in [0, 1].

    Returns:
        Dict with:
        - raw_response: float
        - surface_response: float (normalized to [0, 1], 1 = global optimum)
        - z: list of unnormalized coordinates
        - classic: float (classic Ackley value)
    """
    # Extract coordinates in order
    z = [-40.0 + 80.0 * x[f"x_{i}"] for i in range(1, 7)]

    classic = ackley_classic(z)
    raw_response = -classic
    surface_response = (raw_response - RAW_RESPONSE_MIN) / SURFACE_DENOMINATOR

    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
        "z": z,
        "classic": classic,
    }


def evaluate_candidate(
    suggestion: dict[str, Any],
    evaluated_cache: set[tuple[float, ...]],
) -> dict[str, Any]:
    """Evaluate a single candidate suggestion.

    Args:
        suggestion: BO-MCP suggestion dict with 'parameter_values' field.
        evaluated_cache: Set of already-evaluated coordinate tuples for deduplication.

    Returns:
        Result dict with status, objective_values, parameter_values for submit_results.
    """
    params = suggestion.get("parameter_values", {})
    coords = tuple(params.get(f"x_{i}", 0.0) for i in range(1, 7))

    # Deduplication check
    if coords in evaluated_cache:
        return {
            "suggestion_id": suggestion.get("suggestion_id"),
            "status": "duplicate",
            "failure_reason": "Candidate coordinates already evaluated",
            "objective_values": {"surface_response": None},
            "parameter_values": {f"x_{i}": coords[i - 1] for i in range(1, 7)},
            "metadata": {"raw_response": None},
        }

    evaluated_cache.add(coords)

    try:
        result = evaluate_ackley(params)
        return {
            "suggestion_id": suggestion.get("suggestion_id"),
            "status": "success",
            "objective_values": {"surface_response": result["surface_response"]},
            "parameter_values": {f"x_{i}": coords[i - 1] for i in range(1, 7)},
            "metadata": {
                "raw_response": result["raw_response"],
                "z": result["z"],
                "classic": result["classic"],
            },
        }
    except Exception as e:
        return {
            "suggestion_id": suggestion.get("suggestion_id"),
            "status": "failed",
            "failure_reason": f"Evaluation error: {e}",
            "objective_values": {"surface_response": None},
            "parameter_values": {f"x_{i}": coords[i - 1] for i in range(1, 7)},
            "metadata": {"raw_response": None},
        }