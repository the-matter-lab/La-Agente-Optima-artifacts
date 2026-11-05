from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import logfire
except Exception:  # noqa: BLE001
    class _LogfireFallback:
        def instrument_requests(self) -> None:
            return None

        def info(self, *args, **kwargs) -> None:
            return None

        def debug(self, *args, **kwargs) -> None:
            return None

    logfire = _LogfireFallback()

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # noqa: BLE001
    def configure_logfire() -> None:
        return None

from .bo import fit_surrogate, score_candidates
from .evaluator import DirectArylationEvaluator
from .space import build_candidate_pool, canonical_key, stratified_initial_design

configure_logfire()
logfire.instrument_requests()

Candidate = Dict[str, object]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result_record(
    attempt_index: int,
    batch_index: int,
    batch_size: int,
    candidate: Candidate,
    outcome: Dict[str, object],
) -> Dict[str, object]:
    record = {
        "evaluation_index": attempt_index,
        "batch_index": batch_index,
        "batch_size": batch_size,
        "parameter_values": {
            "base": candidate["base"],
            "ligand": candidate["ligand"],
            "solvent": candidate["solvent"],
            "concentration": float(candidate["concentration"]),
            "temperature_c": int(candidate["temperature_c"]),
        },
        "status": outcome["status"],
        "recorded_at": _utc_now(),
    }
    if outcome["status"] == "success":
        record["objective_values"] = outcome["objective_values"]
    else:
        record["failure_reason"] = outcome.get("failure_reason", "unknown_failure")
    return record


def _save_results(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _best_success(results: List[Dict[str, object]]) -> tuple[Optional[float], Optional[Candidate]]:
    successes = [r for r in results if r["status"] == "success"]
    if not successes:
        return None, None
    best = max(successes, key=lambda r: r["objective_values"]["yield"])
    return float(best["objective_values"]["yield"]), best["parameter_values"]


def _sorted_success_candidates(results: List[Dict[str, object]]) -> List[Candidate]:
    successes = [r for r in results if r["status"] == "success"]
    successes.sort(key=lambda r: r["objective_values"]["yield"], reverse=True)
    return [r["parameter_values"] for r in successes]


def _success_training_data(results: List[Dict[str, object]]) -> tuple[List[Candidate], List[float]]:
    xs = []
    ys = []
    for record in results:
        if record["status"] == "success":
            xs.append(record["parameter_values"])
            ys.append(float(record["objective_values"]["yield"]))
    return xs, ys


def _build_summary(case_id: str, results: List[Dict[str, object]]) -> Dict[str, object]:
    completed = len(results)
    successful = sum(1 for r in results if r["status"] == "success")
    attempted = completed
    best_value, best_parameters = _best_success(results)
    return {
        "case_id": case_id,
        "objective_name": "yield",
        "objective_direction": "maximize",
        "objective_unit": "percent",
        "completed_evaluations": completed,
        "attempted_evaluations": attempted,
        "successful_evaluations": successful,
        "best_objective_value": best_value,
        "best_parameters": best_parameters,
        "results": results,
    }


def run_campaign(
    budget: int = 60,
    seed: int = 818064,
    case_id: str = "direct_arylation",
    results_path: str = "local_results.json",
    manifest_path: str = "campaign_manifest.json",
    preflight: bool = False,
) -> Dict[str, object]:
    logfire.info("starting direct arylation campaign", budget=budget, seed=seed, preflight=preflight)
    if budget <= 0:
        raise ValueError("budget must be positive")
    if preflight:
        payload = {
            "case_id": case_id,
            "objective_name": "yield",
            "objective_direction": "maximize",
            "objective_unit": "percent",
            "planned_budget": budget,
            "environment": {
                "DIRECT_ARYLATION_API_URL_set": bool(os.getenv("DIRECT_ARYLATION_API_URL")),
            },
            "search_space": {
                "parameters": ["base", "ligand", "solvent", "concentration", "temperature_c"],
                "search_space_size": 1728,
            },
            "execution": {
                "strategy": "12-point stratified random initial design followed by random-forest UCB with mutation and random candidate pools",
                "results_path": results_path,
                "manifest_path": manifest_path,
            },
            "checked_at": _utc_now(),
        }
        _save_results(Path("preflight_summary.json"), payload)
        return payload

    rng = random.Random(seed)
    evaluator = DirectArylationEvaluator(timeout_s=30.0)
    results: List[Dict[str, object]] = []
    tried_keys = set()
    initial_design = stratified_initial_design(rng, n=min(12, budget))
    batch_index = 0

    while len(results) < budget:
        if len(results) < len(initial_design):
            candidate = initial_design[len(results)]
        else:
            train_x, train_y = _success_training_data(results)
            top_candidates = _sorted_success_candidates(results)
            pool = build_candidate_pool(rng, tried_keys, top_candidates, pool_size=256)
            if len(train_y) >= 5:
                bundle = fit_surrogate(train_x, train_y, seed + len(results))
                mean, std, optimistic = score_candidates(bundle, pool)
                noise = [rng.random() * 1e-6 for _ in pool]
                scored = list(zip(pool, mean.tolist(), std.tolist(), optimistic.tolist(), noise))
                scored.sort(key=lambda item: (item[3], item[1], item[2], item[4]), reverse=True)
                candidate = scored[0][0]
                logfire.debug(
                    "selected model-guided candidate",
                    attempt=len(results) + 1,
                    optimistic_score=scored[0][3],
                    predicted_mean=scored[0][1],
                    predicted_std=scored[0][2],
                )
            else:
                candidate = pool[0]
                logfire.debug("selected random candidate due to sparse data", attempt=len(results) + 1)

        key = canonical_key(candidate)
        if key in tried_keys:
            raise RuntimeError("internal error: duplicate candidate selected")
        tried_keys.add(key)
        outcome = evaluator.evaluate(candidate)
        batch_index += 1
        record = _result_record(len(results) + 1, batch_index, 1, candidate, outcome)
        results.append(record)

        summary = _build_summary(case_id, results)
        _save_results(Path(results_path), summary)
        best_value = summary["best_objective_value"]
        logfire.info(
            "evaluation complete",
            attempt=len(results),
            status=outcome["status"],
            best_objective_value=best_value,
            candidate=record["parameter_values"],
        )

    final_payload = _build_summary(case_id, results)
    _save_results(Path(results_path), final_payload)
    manifest = {
        "package_modules": [
            "direct_arylation_campaign.__init__",
            "direct_arylation_campaign.space",
            "direct_arylation_campaign.bo",
            "direct_arylation_campaign.evaluator",
            "direct_arylation_campaign.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_campaign.py",
        "latest_local_results": results_path,
        "updated_at": _utc_now(),
    }
    Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return final_payload
