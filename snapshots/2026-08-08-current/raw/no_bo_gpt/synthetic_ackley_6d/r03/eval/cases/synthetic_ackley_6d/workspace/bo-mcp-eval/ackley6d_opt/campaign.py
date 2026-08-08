from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

from .bo import LocalGaussianProcessBO
from .objective import PARAMETER_NAMES, evaluate_ackley
from .reporting import render_results_table, write_json


@dataclass
class CampaignConfig:
    case_id: str = "synthetic_ackley_6d"
    objective_name: str = "surface_response"
    objective_direction: str = "maximize"
    objective_unit: str = "normalized_unitless"
    dimension: int = 6
    seed: int = 20260730
    budget: int = 60
    init_size: int = 12
    acquisition_samples: int = 4096
    results_path: str = "local_results.json"
    manifest_path: str = "campaign_manifest.json"


class Ackley6DCampaign:
    def __init__(self, config: CampaignConfig) -> None:
        self.config = config
        bounds = [(0.0, 1.0)] * config.dimension
        self.optimizer = LocalGaussianProcessBO(
            dim=config.dimension,
            bounds=bounds,
            seed=config.seed,
            init_size=config.init_size,
            acquisition_samples=config.acquisition_samples,
        )

    def run(self) -> Dict:
        seen = set()
        X: List[np.ndarray] = []
        y: List[float] = []
        results: List[Dict] = []

        initial_batch = self.optimizer.initial_design(seen=seen, n_points=self.config.init_size)
        for suggestion in initial_batch:
            record = self._evaluate_candidate(suggestion.x, len(results), batch_index=0, batch_size=len(initial_batch))
            results.append(record)
            seen.add(self.optimizer.key_for(suggestion.x))
            if record["status"] == "success":
                X.append(suggestion.x)
                y.append(record["objective_values"][self.config.objective_name])

        batch_index = 1
        while len(results) < self.config.budget:
            suggestion = self.optimizer.suggest(np.asarray(X), np.asarray(y), seen=seen)
            record = self._evaluate_candidate(suggestion.x, len(results), batch_index=batch_index, batch_size=1)
            results.append(record)
            seen.add(self.optimizer.key_for(suggestion.x))
            if record["status"] == "success":
                X.append(suggestion.x)
                y.append(record["objective_values"][self.config.objective_name])
            batch_index += 1

        successful = [r for r in results if r["status"] == "success"]
        best = max(successful, key=lambda r: r["objective_values"][self.config.objective_name])
        payload = {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "seed": self.config.seed,
            "budget": self.config.budget,
            "initialization_strategy": "latin_hypercube_random_initial_design",
            "initialization_size": self.config.init_size,
            "acquisition_strategy": "gaussian_process_expected_improvement",
            "backend": "local_python_gp_bo",
            "attempted_evaluations": len(results),
            "completed_evaluations": len(successful),
            "successful_evaluations": len(successful),
            "failed_evaluations": len(results) - len(successful),
            "best_objective_value": best["objective_values"][self.config.objective_name],
            "best_parameters": best["parameter_values"],
            "best_raw_response": best["raw_response"],
            "results": results,
        }
        write_json(self.config.results_path, payload)
        write_json(
            self.config.manifest_path,
            {
                "package": "ackley6d_opt",
                "modules": [
                    "ackley6d_opt.campaign",
                    "ackley6d_opt.bo",
                    "ackley6d_opt.objective",
                    "ackley6d_opt.reporting",
                ],
                "run_entrypoint": "run_ackley6d_opt.py",
                "latest_local_results": str(Path(self.config.results_path).resolve()),
            },
        )
        payload["results_table"] = render_results_table(results)
        return payload

    def _evaluate_candidate(self, x: np.ndarray, evaluation_index: int, batch_index: int, batch_size: int) -> Dict:
        parameter_values = {name: float(value) for name, value in zip(PARAMETER_NAMES, x.tolist())}
        try:
            raw_response, surface_response = evaluate_ackley(parameter_values)
            return {
                "evaluation_index": evaluation_index,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "parameter_values": parameter_values,
                "objective_values": {self.config.objective_name: float(surface_response)},
                "status": "success",
                "failure_reason": None,
                "raw_response": float(raw_response),
                "objective_unit": self.config.objective_unit,
            }
        except Exception as exc:  # pragma: no cover
            return {
                "evaluation_index": evaluation_index,
                "batch_index": batch_index,
                "batch_size": batch_size,
                "parameter_values": parameter_values,
                "objective_values": {},
                "status": "failed",
                "failure_reason": str(exc),
                "raw_response": None,
                "objective_unit": self.config.objective_unit,
            }
