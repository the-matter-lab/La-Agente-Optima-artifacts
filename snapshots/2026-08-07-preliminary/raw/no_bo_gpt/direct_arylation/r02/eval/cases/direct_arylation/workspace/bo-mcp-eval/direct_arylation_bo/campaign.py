from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .bo import BayesianLinearThompson, BayesianLinearThompsonConfig
from .evaluator import OracleEvaluator, SyntheticSmokeEvaluator
from .space import OneHotInteractionEncoder, candidate_key, sample_random_candidates


@dataclass
class CampaignConfig:
    case_id: str = "direct_arylation_reaction_yield_optimization"
    cache_buster_nonce: str = ""
    objective_name: str = "yield"
    objective_direction: str = "maximize"
    objective_unit: str = "percent"
    budget: int = 60
    initial_random: int = 12
    batch_size: int = 2
    pool_size: int = 256
    random_seed: int = 20260730
    smoke_test: bool = False
    output_path: str = "local_results.json"
    manifest_path: str = "campaign_manifest.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _build_summary(config: CampaignConfig, results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in results if record["status"] == "success"]
    failed = [record for record in results if record["status"] != "success"]
    best_record = None
    if successful:
        best_record = max(successful, key=lambda record: record["objective_values"][config.objective_name])
    summary: dict[str, Any] = {
        "case_id": config.case_id,
        "cache_buster_nonce": config.cache_buster_nonce,
        "objective_name": config.objective_name,
        "objective_direction": config.objective_direction,
        "objective_unit": config.objective_unit,
        "attempted_evaluations": len(results),
        "successful_evaluations": len(successful),
        "completed_evaluations": len(successful),
        "failed_evaluations": len(failed),
        "best_objective_value": None if best_record is None else best_record["objective_values"][config.objective_name],
        "best_parameters": None if best_record is None else best_record["parameter_values"],
        "results": results,
    }
    return summary


def _write_manifest(config: CampaignConfig, latest_result_path: Path) -> None:
    manifest = {
        "package": "direct_arylation_bo",
        "modules": [
            "direct_arylation_bo.__init__",
            "direct_arylation_bo.space",
            "direct_arylation_bo.bo",
            "direct_arylation_bo.evaluator",
            "direct_arylation_bo.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_bo.py",
        "latest_local_results": str(latest_result_path),
    }
    _write_json(Path(config.manifest_path), manifest)


def run_campaign(config: CampaignConfig) -> dict[str, Any]:
    rng = np.random.default_rng(config.random_seed)
    encoder = OneHotInteractionEncoder.build()
    model = BayesianLinearThompson(
        encoder=encoder,
        rng=rng,
        config=BayesianLinearThompsonConfig(pool_size=config.pool_size),
    )
    evaluator = SyntheticSmokeEvaluator() if config.smoke_test else OracleEvaluator.from_environment()
    results: list[dict[str, Any]] = []
    observed_candidates: list[dict[str, Any]] = []
    observed_yields: list[float] = []
    seen_keys: set[tuple[Any, ...]] = set()

    def persist() -> dict[str, Any]:
        summary = _build_summary(config, results)
        _write_json(Path(config.output_path), summary)
        _write_manifest(config, Path(config.output_path))
        return summary

    attempted = 0
    batch_index = 0
    while attempted < config.budget:
        remaining = config.budget - attempted
        if attempted == 0:
            current_batch_size = min(config.initial_random, remaining)
            candidates = sample_random_candidates(rng=rng, n=current_batch_size, exclude=seen_keys)
        else:
            current_batch_size = min(config.batch_size, remaining)
            model.fit(observed_candidates, observed_yields)
            candidates = model.suggest_batch(seen_keys=seen_keys, batch_size=current_batch_size)
        batch_results = evaluator.evaluate_batch(candidates)
        for idx_in_batch, record in enumerate(batch_results, start=1):
            key = candidate_key(record["parameter_values"])
            seen_keys.add(key)
            attempted += 1
            enriched = {
                "evaluation_index": attempted,
                "batch_index": batch_index,
                "batch_size": current_batch_size,
                **record,
            }
            results.append(enriched)
            if record["status"] == "success":
                observed_candidates.append(record["parameter_values"])
                observed_yields.append(record["objective_values"][config.objective_name])
            elif "failure_reason" not in enriched:
                enriched["failure_reason"] = "Unknown failure"
        persist()
        batch_index += 1

    return persist()
