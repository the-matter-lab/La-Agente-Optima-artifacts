"""Extract objective values from an evaluator result dict."""

from __future__ import annotations


def extract_objective_values(eval_result: dict[str, object]) -> dict[str, float]:
    """Return the ``objective_values`` dict for BO-MCP submission."""
    return {"surface_response": float(eval_result["surface_response"])}


def extract_raw_response(eval_result: dict[str, object]) -> float:
    """Return the raw Ackley response (for reporting)."""
    return float(eval_result["raw_response"])