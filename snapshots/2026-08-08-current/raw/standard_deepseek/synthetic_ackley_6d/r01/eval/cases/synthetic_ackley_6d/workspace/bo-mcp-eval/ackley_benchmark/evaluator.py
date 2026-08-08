"""Deterministic Ackley-6D evaluator — no chemistry, no PySCF."""

from __future__ import annotations

import math

# Normalisation constants (user-provided)
_WORST_RAW: float = -22.350402387287602
_BEST_RAW: float = 0.0
_D: int = 6


def evaluate(parameter_values: dict[str, float]) -> dict[str, object]:
    """Evaluate the Ackley function at the given normalised coordinates.

    Parameters
    ----------
    parameter_values : dict[str, float]
        Keys ``x_1`` … ``x_6``, each in [0, 1].

    Returns
    -------
    dict
        ``raw_response`` (float), ``surface_response`` (float), ``status`` (str).
    """
    z = [_to_ackley_domain(parameter_values[f"x_{i}"]) for i in range(1, _D + 1)]

    sum_sq = sum(v * v for v in z)
    sum_cos = sum(math.cos(2.0 * math.pi * v) for v in z)

    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum_sq / _D))
        - math.exp(sum_cos / _D)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - _WORST_RAW) / (_BEST_RAW - _WORST_RAW)

    return {
        "raw_response": raw_response,
        "surface_response": surface_response,
        "status": "success",
    }


def _to_ackley_domain(x: float) -> float:
    """Map normalised [0, 1] → Ackley domain [-40, 40]."""
    return -40.0 + 80.0 * x