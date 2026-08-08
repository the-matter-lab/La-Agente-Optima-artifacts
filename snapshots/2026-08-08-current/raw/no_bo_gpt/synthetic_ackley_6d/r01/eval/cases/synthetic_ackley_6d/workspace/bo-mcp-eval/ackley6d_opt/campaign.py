from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from .bo import LocalBayesOptimizer
from .objective import surface_response


@dataclass
class CampaignConfig:
    case_id: str
    cache_buster_nonce: str
    objective_name: str = "surface_response"
    objective_direction: str = "maximize"
    objective_unit: str = "normalized_unitless"
    dimensions: int = 6
    lower_bound: float = 0.0
    upper_bound: float = 1.0
    budget: int = 60
    initial_design_size: int = 11
    candidate_pool_size: int = 8192
    seed: int = 20260730
    acquisition: str = "expected_improvement"
    output_path: str = "local_results.json"


def _param_dict(x: List[float]) -> Dict[str, float]:
    return {f"x_{i + 1}": float(v) for i, v in enumerate(x)}


def run_campaign(config: CampaignConfig) -> Dict[str, Any]:
    optimizer = LocalBayesOptimizer(
        dim=config.dimensions,
        seed=config.seed,
        initial_design_size=config.initial_design_size,
        candidate_pool_size=config.candidate_pool_size,
        jitter=0.01,
    )

    results: List[Dict[str, Any]] = []
    completed_x: List[List[float]] = []
    completed_y: List[float] = []
    best_result: Dict[str, Any] | None = None

    initial_batch = optimizer.initial_design()
    suggestions = list(initial_batch)

    while len(results) < config.budget:
        if not suggestions:
            suggestion = optimizer.suggest(completed_x, completed_y)
            suggestions = [suggestion]

        batch = suggestions
        suggestions = []
        batch_index = len(results)
        batch_size = len(batch)

        for suggestion in batch:
            evaluation_index = len(results)
            x = suggestion.x
            values = surface_response(x)
            objective_value = float(values[config.objective_name])

            record = {
                "evaluation_index": evaluation_index,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "parameter_values": _param_dict(x),
                "objective_values": {config.objective_name: objective_value},
                "status": "success",
                "failure_reason": None,
                "raw_response": float(values["raw_response"]),
                "classic": float(values["classic"]),
                config.objective_name: objective_value,
                "candidate_source": suggestion.source,
                "acquisition_value": suggestion.acquisition_value,
            }
            results.append(record)
            completed_x.append(x)
            completed_y.append(objective_value)

            if best_result is None or objective_value > best_result[config.objective_name]:
                best_result = record

            if len(results) >= config.budget:
                break

    if best_result is None:
        raise RuntimeError("No successful evaluations were completed.")

    artifact = {
        "case_id": config.case_id,
        "cache_buster_nonce": config.cache_buster_nonce,
        "objective_name": config.objective_name,
        "objective_direction": config.objective_direction,
        "objective_unit": config.objective_unit,
        "dimensions": config.dimensions,
        "search_space": {
            f"x_{i + 1}": {"type": "continuous", "lower": config.lower_bound, "upper": config.upper_bound}
            for i in range(config.dimensions)
        },
        "backend": "local_python_gp_bo",
        "random_seed": config.seed,
        "initialization_strategy": "sobol",
        "initial_design_size": config.initial_design_size,
        "acquisition_strategy": config.acquisition,
        "candidate_pool_size": config.candidate_pool_size,
        "attempted_evaluations": len(results),
        "completed_evaluations": sum(1 for r in results if r["status"] == "success"),
        "successful_evaluations": sum(1 for r in results if r["status"] == "success"),
        "failed_evaluations": sum(1 for r in results if r["status"] != "success"),
        "best_objective_value": float(best_result[config.objective_name]),
        "best_parameters": best_result["parameter_values"],
        "best_raw_response": float(best_result["raw_response"]),
        "results": results,
        "config": asdict(config),
    }

    output_path = Path(config.output_path)
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact
