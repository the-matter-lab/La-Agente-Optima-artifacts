from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .bo import BOSuggester, SuggestionConfig
from .oracle import DirectArylationOracle, MockOracle
from .space import SearchSpace


@dataclass
class CampaignConfig:
    case_id: str
    objective_name: str = "yield"
    objective_direction: str = "maximize"
    objective_unit: str = "percent"
    budget: int = 60
    seed: int = 20260730
    smoke_test: bool = False
    cache_buster_nonce: str = ""
    local_results_path: str = "local_results.json"
    manifest_path: str = "campaign_manifest.json"


def run_campaign(config: CampaignConfig) -> Dict[str, object]:
    rng = random.Random(config.seed)
    space = SearchSpace()
    suggester = BOSuggester(space=space, config=SuggestionConfig(), rng=rng)
    oracle = MockOracle() if config.smoke_test else DirectArylationOracle()

    results: List[Dict[str, object]] = []
    best_value: Optional[float] = None
    best_parameters: Optional[Dict[str, object]] = None

    for eval_idx in range(1, config.budget + 1):
        candidate = suggester.suggest(results)
        outcome = oracle.evaluate(candidate)
        record: Dict[str, object] = {
            "evaluation_index": eval_idx,
            "batch_index": eval_idx,
            "batch_size": 1,
            "parameter_values": candidate.to_parameter_values(),
            "status": outcome.status,
            "objective_values": {},
            "failure_reason": outcome.failure_reason,
        }
        if outcome.status == "success" and outcome.objective_value is not None:
            record["objective_values"] = {config.objective_name: outcome.objective_value}
            record["failure_reason"] = None
            if best_value is None or outcome.objective_value > best_value:
                best_value = outcome.objective_value
                best_parameters = candidate.to_parameter_values()
        results.append(record)

    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful
    payload: Dict[str, object] = {
        "case_id": config.case_id,
        "cache_buster_nonce": config.cache_buster_nonce,
        "objective_name": config.objective_name,
        "objective_direction": config.objective_direction,
        "objective_unit": config.objective_unit,
        "attempted_evaluations": len(results),
        "completed_evaluations": successful,
        "successful_evaluations": successful,
        "failed_evaluations": failed,
        "best_objective_value": best_value,
        "best_parameters": best_parameters,
        "results": results,
    }

    results_path = Path(config.local_results_path)
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    manifest = {
        "package": "direct_arylation_bo",
        "modules": [
            "direct_arylation_bo.space",
            "direct_arylation_bo.oracle",
            "direct_arylation_bo.bo",
            "direct_arylation_bo.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_bo.py",
        "latest_local_results": str(results_path),
    }
    Path(config.manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return payload


def build_config(
    *,
    budget: int,
    seed: int,
    smoke_test: bool,
    cache_buster_nonce: str,
    results_path: str,
    manifest_path: str,
) -> CampaignConfig:
    case_id = "direct_arylation_reaction_yield_optimization"
    return CampaignConfig(
        case_id=case_id,
        budget=budget,
        seed=seed,
        smoke_test=smoke_test,
        cache_buster_nonce=cache_buster_nonce,
        local_results_path=results_path,
        manifest_path=manifest_path,
    )
