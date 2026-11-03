from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    import logfire
    from grafico.core.logfire_config import configure_logfire

    configure_logfire()
    logfire.instrument_requests()
except Exception:  # pragma: no cover
    logfire = None

from .bo import BOConfig, LocalBayesOptimizer
from .objective import PARAMETER_NAMES, evaluate_surface


@dataclass
class CampaignConfig:
    case_id: str = "synthetic_ackley_6d"
    objective_name: str = "surface_response"
    objective_direction: str = "maximize"
    objective_unit: str = "normalized_unitless"
    total_budget: int = 60
    seed: int = 20260812
    initial_design_size: int = 12
    candidate_pool_size: int = 4096
    acquisition_strategy: str = "gaussian_process_expected_improvement"
    batch_size: int = 1
    output_path: str = "local_results.json"


class Ackley6DCampaign:
    def __init__(self, config: CampaignConfig):
        self.config = config
        bo_config = BOConfig(
            seed=config.seed,
            dimensions=6,
            initial_design_size=config.initial_design_size,
            candidate_pool_size=config.candidate_pool_size,
        )
        self.optimizer = LocalBayesOptimizer(bo_config)
        self.results: List[Dict] = []

    def preflight_summary(self) -> Dict:
        return {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "dimensions": len(PARAMETER_NAMES),
            "parameter_names": PARAMETER_NAMES,
            "total_budget": self.config.total_budget,
            "seed": self.config.seed,
            "initial_design_size": self.config.initial_design_size,
            "candidate_pool_size": self.config.candidate_pool_size,
            "acquisition_strategy": self.config.acquisition_strategy,
            "batch_size": self.config.batch_size,
            "output_path": self.config.output_path,
        }

    def _log(self, level: str, message: str, **kwargs) -> None:
        if logfire is not None:
            getattr(logfire, level)(message, **kwargs)

    def _evaluate_once(self, parameter_values: Dict[str, float], evaluation_index: int) -> Dict:
        row = {
            "evaluation_index": evaluation_index,
            "batch_index": evaluation_index,
            "batch_size": self.config.batch_size,
            "parameter_values": parameter_values,
            "objective_values": {},
            "status": "failed",
            "failure_reason": None,
            "raw_response": None,
        }
        try:
            metrics = evaluate_surface(parameter_values)
            row["objective_values"] = {self.config.objective_name: metrics[self.config.objective_name]}
            row["raw_response"] = metrics["raw_response"]
            row["status"] = "success"
        except Exception as exc:  # pragma: no cover
            row["failure_reason"] = f"{type(exc).__name__}: {exc}"
        return row

    def run(self) -> Dict:
        self._log("info", "Starting Ackley 6D campaign", budget=self.config.total_budget, seed=self.config.seed)
        for evaluation_index in range(1, self.config.total_budget + 1):
            params = self.optimizer.suggest(self.results)
            row = self._evaluate_once(params, evaluation_index)
            self.results.append(row)
            if row["status"] == "success":
                score = row["objective_values"][self.config.objective_name]
                self._log("info", "Completed evaluation", evaluation_index=evaluation_index, objective_value=score)
            else:
                self._log("info", "Evaluation failed", evaluation_index=evaluation_index, failure_reason=row["failure_reason"])

        summary = self.build_summary()
        Path(self.config.output_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def build_summary(self) -> Dict:
        successful_rows = [row for row in self.results if row["status"] == "success"]
        attempted = len(self.results)
        successful = len(successful_rows)
        best_row: Optional[Dict] = None
        if successful_rows:
            best_row = max(successful_rows, key=lambda row: row["objective_values"][self.config.objective_name])
        return {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "completed_evaluations": successful,
            "attempted_evaluations": attempted,
            "successful_evaluations": successful,
            "failed_evaluations": attempted - successful,
            "best_objective_value": None if best_row is None else best_row["objective_values"][self.config.objective_name],
            "best_parameters": None if best_row is None else best_row["parameter_values"],
            "best_raw_response": None if best_row is None else best_row["raw_response"],
            "best_surface_response": None if best_row is None else best_row["objective_values"][self.config.objective_name],
            "seed": self.config.seed,
            "initial_design_size": self.config.initial_design_size,
            "candidate_pool_size": self.config.candidate_pool_size,
            "acquisition_strategy": self.config.acquisition_strategy,
            "search_space": {
                name: {"type": "continuous", "lower": 0.0, "upper": 1.0}
                for name in PARAMETER_NAMES
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "results": self.results,
        }


def write_manifest(package_dir: str, output_path: str) -> None:
    manifest = {
        "package_modules": [
            f"{package_dir}.__init__",
            f"{package_dir}.objective",
            f"{package_dir}.bo",
            f"{package_dir}.campaign",
        ],
        "run_entrypoint": "run_ackley6d_opt.py",
        "latest_local_results": output_path,
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
