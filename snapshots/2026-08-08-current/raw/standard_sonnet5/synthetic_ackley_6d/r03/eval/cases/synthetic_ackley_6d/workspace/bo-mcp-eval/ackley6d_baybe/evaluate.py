"""Candidate evaluation for the Ackley-6D synthetic benchmark.

Pure/deterministic math only -- no PySCF, CREST, MOF, RAISE, RoboFlex, or
any other chemistry/experimental evaluator is called here. Failures (e.g.
a malformed suggestion payload) are caught and reported, never raised, so
the campaign loop can record them and keep going within budget.
"""
import math

from .objective import OBJECTIVE_NAME, compute_surface_response
from .search_space import PARAMETER_NAMES


def evaluate_candidate(parameter_values: dict) -> dict:
    """Evaluate one candidate point; never raises."""
    try:
        for name in PARAMETER_NAMES:
            value = float(parameter_values[name])
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name}={value} outside [0.0, 1.0]")
        raw_response, surface_response = compute_surface_response(parameter_values)
        if not math.isfinite(raw_response) or not math.isfinite(surface_response):
            raise ValueError("non-finite objective value computed")
        return {
            "status": "success",
            "raw_response": raw_response,
            "objective_values": {OBJECTIVE_NAME: surface_response},
            "failure_reason": None,
        }
    except Exception as exc:  # noqa: BLE001 - report any failure, keep loop alive
        return {
            "status": "failed",
            "raw_response": None,
            "objective_values": None,
            "failure_reason": str(exc),
        }
