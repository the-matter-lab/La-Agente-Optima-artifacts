from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .bo import BOConfig, LocalBayesOptimizer, point_key
from .objective import evaluate_surface

try:
    import logfire
    from grafico.core.logfire_config import configure_logfire

    configure_logfire()
    logfire.instrument_requests()
except Exception:  # pragma: no cover
    class _DummyLogfire:
        @staticmethod
        def info(*args, **kwargs):
            return None

        @staticmethod
        def debug(*args, **kwargs):
            return None

    logfire = _DummyLogfire()


@dataclass
class CampaignConfig:
    case_id: str = "synthetic_ackley_6d"
    objective_name: str = "surface_response"
    objective_direction: str = "maximize"
    objective_unit: str = "normalized_unitless"
    seed: int = 731245
    budget: int = 60
    init_size: int = 16
    candidate_pool_size: int = 4096
    local_results_path: str = "local_results.json"
    table_csv_path: str = "ackley6d_evaluations.csv"


class Ackley6DCampaign:
    def __init__(self, config: CampaignConfig):
        if config.budget != 60:
            raise ValueError("This benchmark must use exactly 60 attempted evaluations")
        if config.init_size <= 0 or config.init_size >= config.budget:
            raise ValueError("init_size must be positive and smaller than budget")
        self.config = config
        self.optimizer = LocalBayesOptimizer(
            BOConfig(
                dim=6,
                budget=config.budget,
                init_size=config.init_size,
                candidate_pool_size=config.candidate_pool_size,
                seed=config.seed,
            )
        )
        self._seen = set()
        self._x_obs: List[np.ndarray] = []
        self._y_obs: List[float] = []
        self.results: List[Dict] = []

    def preflight(self) -> Dict[str, object]:
        info = {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "budget": self.config.budget,
            "init_size": self.config.init_size,
            "candidate_pool_size": self.config.candidate_pool_size,
            "seed": self.config.seed,
            "outputs": {
                "local_results_path": self.config.local_results_path,
                "table_csv_path": self.config.table_csv_path,
            },
        }
        logfire.info("Ackley 6D preflight complete", **info)
        return info

    def _record_success(self, params: Dict[str, float], batch_index: int, batch_size: int) -> None:
        metrics = evaluate_surface(params)
        result = {
            "evaluation_index": len(self.results) + 1,
            "batch_index": batch_index,
            "batch_size": batch_size,
            "parameter_values": params,
            "objective_values": {self.config.objective_name: metrics[self.config.objective_name]},
            "status": "success",
            "failure_reason": None,
            "raw_response": metrics["raw_response"],
            "objective_unit": self.config.objective_unit,
        }
        self.results.append(result)
        x = np.asarray([params[f"x_{i}"] for i in range(1, 7)], dtype=float)
        self._x_obs.append(x)
        self._y_obs.append(float(metrics[self.config.objective_name]))
        self._seen.add(point_key(x))
        logfire.debug(
            "Recorded Ackley evaluation",
            evaluation_index=result["evaluation_index"],
            batch_index=batch_index,
            objective_value=result["objective_values"][self.config.objective_name],
        )

    def _to_params(self, x: np.ndarray) -> Dict[str, float]:
        return {f"x_{i+1}": float(x[i]) for i in range(6)}

    def run(self) -> Dict[str, object]:
        init = self.optimizer.initial_design()
        for x in init:
            if len(self.results) >= self.config.budget:
                break
            self._record_success(self._to_params(x), batch_index=0, batch_size=len(init))

        while len(self.results) < self.config.budget:
            x_obs = np.vstack(self._x_obs)
            y_obs = np.asarray(self._y_obs, dtype=float)
            suggestion = self.optimizer.suggest(x_obs, y_obs, self._seen)
            self._record_success(self._to_params(suggestion), batch_index=len(self.results) - len(init) + 1, batch_size=1)

        return self.write_outputs()

    def write_outputs(self) -> Dict[str, object]:
        best_result = max(self.results, key=lambda r: r["objective_values"][self.config.objective_name])
        completed = sum(1 for r in self.results if r["status"] == "success")
        attempted = len(self.results)
        payload = {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "seed": self.config.seed,
            "budget": self.config.budget,
            "completed_evaluations": completed,
            "attempted_evaluations": attempted,
            "successful_evaluations": completed,
            "failed_evaluations": attempted - completed,
            "best_objective_value": best_result["objective_values"][self.config.objective_name],
            "best_parameters": best_result["parameter_values"],
            "best_raw_response": best_result["raw_response"],
            "results": self.results,
        }
        Path(self.config.local_results_path).write_text(json.dumps(payload, indent=2))
        with Path(self.config.table_csv_path).open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "evaluation_index",
                "batch_index",
                "batch_size",
                "x_1",
                "x_2",
                "x_3",
                "x_4",
                "x_5",
                "x_6",
                "raw_response",
                self.config.objective_name,
                "status",
                "failure_reason",
            ])
            for row in self.results:
                params = row["parameter_values"]
                writer.writerow([
                    row["evaluation_index"],
                    row["batch_index"],
                    row["batch_size"],
                    params["x_1"],
                    params["x_2"],
                    params["x_3"],
                    params["x_4"],
                    params["x_5"],
                    params["x_6"],
                    row["raw_response"],
                    row["objective_values"][self.config.objective_name],
                    row["status"],
                    row["failure_reason"],
                ])
        return payload
