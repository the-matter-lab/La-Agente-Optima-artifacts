from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import logfire
import numpy as np

from .oracle import DirectArylationOracle, MockOracle
from .search_space import SearchSpace
from .surrogate import SuggestionEngine


@dataclass
class CampaignConfig:
    case_id: str
    budget: int = 60
    init_batch_size: int = 12
    guided_batch_size: int = 4
    seed: int = 20260812
    objective_name: str = "yield"
    objective_direction: str = "maximize"
    objective_unit: str = "percent"
    api_url: Optional[str] = None
    live: bool = True
    output_path: str = "local_results.json"


class DirectArylationCampaign:
    def __init__(self, config: CampaignConfig):
        self.config = config
        self.space = SearchSpace()
        self.rng = np.random.default_rng(config.seed)
        self.suggester = SuggestionEngine(seed=config.seed)
        if config.live:
            if not config.api_url:
                raise ValueError("DIRECT_ARYLATION_API_URL is required for live execution")
            self.oracle = DirectArylationOracle(config.api_url)
        else:
            self.oracle = MockOracle()
        self.all_candidates = self.space.all_candidates()
        self.results: List[Dict[str, object]] = []
        self.seen_keys = set()

    def run(self) -> Dict[str, object]:
        logfire.info(
            "starting direct arylation campaign",
            budget=self.config.budget,
            live=self.config.live,
            seed=self.config.seed,
        )
        plan = self._batch_plan()
        remaining = list(self.all_candidates)
        successes_candidates: List[Dict[str, object]] = []
        successes_values: List[float] = []

        for batch_index, batch_size in enumerate(plan, start=1):
            if len(self.results) >= self.config.budget:
                break
            if batch_index == 1:
                chosen = self._random_unique_sample(remaining, batch_size)
            else:
                chosen = self.suggester.suggest(
                    observed_candidates=successes_candidates,
                    observed_values=successes_values,
                    remaining_candidates=remaining,
                    batch_size=batch_size,
                    rng=self.rng,
                    space=self.space,
                )
            logfire.info(
                "evaluating batch",
                batch_index=batch_index,
                batch_size=len(chosen),
                attempted_before=len(self.results),
            )
            for candidate in chosen:
                rec = self._evaluate_one(candidate, batch_index=batch_index, batch_size=len(chosen))
                remaining = [c for c in remaining if self.space.key(c) != self.space.key(candidate)]
                if rec["status"] == "completed":
                    successes_candidates.append(candidate)
                    successes_values.append(float(rec["objective_values"][self.config.objective_name]))
                if len(self.results) >= self.config.budget:
                    break

        artifact = self._build_artifact()
        self._write_artifact(artifact)
        return artifact

    def _batch_plan(self) -> List[int]:
        plan = [self.config.init_batch_size]
        remaining = self.config.budget - self.config.init_batch_size
        while remaining > 0:
            step = min(self.config.guided_batch_size, remaining)
            plan.append(step)
            remaining -= step
        return plan

    def _random_unique_sample(self, remaining: Sequence[Dict[str, object]], n: int) -> List[Dict[str, object]]:
        idxs = self.rng.choice(len(remaining), size=n, replace=False)
        return [remaining[int(i)] for i in idxs]

    def _evaluate_one(self, candidate: Dict[str, object], batch_index: int, batch_size: int) -> Dict[str, object]:
        key = self.space.key(candidate)
        if key in self.seen_keys:
            raise RuntimeError(f"duplicate candidate selected: {key}")
        self.seen_keys.add(key)
        status, value, failure_reason = self.oracle.evaluate(candidate)
        result: Dict[str, object] = {
            "evaluation_index": len(self.results) + 1,
            "batch_index": batch_index,
            "batch_size": batch_size,
            "parameter_values": self.space.to_parameter_values(candidate),
            "status": status,
        }
        if status == "completed" and value is not None:
            result["objective_values"] = {self.config.objective_name: round(float(value), 2)}
            current_best = self._current_best_value()
            better = current_best is None or float(value) > current_best
            logfire.info(
                "evaluation completed",
                evaluation_index=result["evaluation_index"],
                yield_value=result["objective_values"][self.config.objective_name],
                improved=better,
            )
        else:
            result["failure_reason"] = failure_reason or "unknown_failure"
            logfire.info(
                "evaluation failed",
                evaluation_index=result["evaluation_index"],
                reason=result["failure_reason"],
            )
        self.results.append(result)
        return result

    def _current_best_value(self) -> Optional[float]:
        vals = [
            float(r["objective_values"][self.config.objective_name])
            for r in self.results
            if r["status"] == "completed" and "objective_values" in r
        ]
        return max(vals) if vals else None

    def _build_artifact(self) -> Dict[str, object]:
        successful = [r for r in self.results if r["status"] == "completed" and "objective_values" in r]
        failed = [r for r in self.results if r["status"] != "completed"]
        if successful:
            best_record = max(successful, key=lambda r: float(r["objective_values"][self.config.objective_name]))
            best_value = float(best_record["objective_values"][self.config.objective_name])
            best_parameters = best_record["parameter_values"]
        else:
            best_value = None
            best_parameters = None
        return {
            "case_id": self.config.case_id,
            "objective_name": self.config.objective_name,
            "objective_direction": self.config.objective_direction,
            "objective_unit": self.config.objective_unit,
            "attempted_evaluations": len(self.results),
            "completed_evaluations": len(successful),
            "failed_evaluations": len(failed),
            "best_objective_value": best_value,
            "best_parameters": best_parameters,
            "results": self.results,
        }

    def _write_artifact(self, artifact: Dict[str, object]) -> None:
        output_path = Path(self.config.output_path)
        output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        manifest = {
            "package_modules": [
                "direct_arylation_bo.search_space",
                "direct_arylation_bo.oracle",
                "direct_arylation_bo.surrogate",
                "direct_arylation_bo.campaign",
            ],
            "run_entrypoint": "run_direct_arylation_bo.py",
            "latest_local_results": str(output_path),
        }
        Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logfire.info("artifacts written", output_path=str(output_path), manifest_path="campaign_manifest.json")


def load_config_from_env(*, live: bool, budget: int, seed: int, output_path: str, case_id: str) -> CampaignConfig:
    return CampaignConfig(
        case_id=case_id,
        budget=budget,
        seed=seed,
        api_url=os.getenv("DIRECT_ARYLATION_API_URL"),
        live=live,
        output_path=output_path,
    )
