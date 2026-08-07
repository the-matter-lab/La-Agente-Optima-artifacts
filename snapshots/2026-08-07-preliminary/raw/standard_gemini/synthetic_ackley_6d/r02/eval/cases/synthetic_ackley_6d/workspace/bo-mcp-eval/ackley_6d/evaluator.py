import logging
from typing import Any, Optional
from ackley_6d.objective import evaluate_ackley_6d

logger = logging.getLogger(__name__)

def evaluate_candidate(
    suggestion: dict[str, Any],
    evaluation_index: int
) -> dict[str, Any]:
    """
    Evaluate a single candidate suggestion.
    Returns a result dictionary with the following structure:
    {
        "evaluation_index": int,
        "suggestion_id": str,
        "parameter_values": dict[str, float],
        "objective_values": dict[str, float] or None,
        "status": str ("success" or "failed"),
        "failure_reason": str or None,
        "raw_response": float or None,
        "classic": float or None
    }
    """
    suggestion_id = suggestion.get("suggestion_id")
    parameter_values = suggestion.get("parameter_values", {})

    # Extract x_1..x_6
    try:
        x = [float(parameter_values[f"x_{i}"]) for i in range(1, 7)]
    except Exception as e:
        logger.error(f"Failed to extract parameters from suggestion: {e}")
        return {
            "evaluation_index": evaluation_index,
            "suggestion_id": suggestion_id,
            "parameter_values": parameter_values,
            "objective_values": None,
            "status": "failed",
            "failure_reason": f"Parameter extraction failed: {str(e)}",
            "raw_response": None,
            "classic": None
        }

    # Evaluate the objective
    try:
        eval_results = evaluate_ackley_6d(x)
        return {
            "evaluation_index": evaluation_index,
            "suggestion_id": suggestion_id,
            "parameter_values": {f"x_{i}": x[i-1] for i in range(1, 7)},
            "objective_values": {"surface_response": eval_results["surface_response"]},
            "status": "success",
            "failure_reason": None,
            "raw_response": eval_results["raw_response"],
            "classic": eval_results["classic"]
        }
    except Exception as e:
        logger.error(f"Objective evaluation failed: {e}")
        return {
            "evaluation_index": evaluation_index,
            "suggestion_id": suggestion_id,
            "parameter_values": {f"x_{i}": x[i-1] for i in range(1, 7)},
            "objective_values": None,
            "status": "failed",
            "failure_reason": f"Evaluation failed: {str(e)}",
            "raw_response": None,
            "classic": None
        }
