from __future__ import annotations

import json
import os
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")

import numpy as np
from sklearn.exceptions import ConvergenceWarning

warnings.filterwarnings("ignore", category=ConvergenceWarning)

try:
    import logfire
except Exception:  # pragma: no cover
    class _DummyLogfire:
        def instrument_requests(self) -> None:
            return None

        def info(self, *args, **kwargs) -> None:
            return None

        def debug(self, *args, **kwargs) -> None:
            return None

    logfire = _DummyLogfire()

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # pragma: no cover
    def configure_logfire() -> None:
        return None

from .bo import SuggestionConfig, latin_hypercube, suggest_batch, unique_key
from .objective import evaluate_ackley_6d

configure_logfire()
logfire.instrument_requests()


@dataclass
class CampaignConfig:
    case_id: str
    objective_name: str = "surface_response"
    objective_direction: str = "maximize"
    objective_unit: str = "normalized_unitless"
    dimensions: int = 6
    total_budget: int = 60
    init_size: int = 12
    batch_schedule: List[int] | None = None
    random_seed: int = 20260730
    candidate_pool_size: int = 4096
    gp_restarts: int = 3
    results_path: str = "local_results.json"

    def __post_init__(self) -> None:
        if self.batch_schedule is None:
            self.batch_schedule = [4] * 12
        if self.init_size + sum(self.batch_schedule) != self.total_budget:
            raise ValueError("init_size + sum(batch_schedule) must equal total_budget")


def _vector_to_params(x: np.ndarray) -> Dict[str, float]:
    return {f"x_{i+1}": float(v) for i, v in enumerate(x.tolist())}


def _record_attempt(
    results: List[Dict[str, Any]],
    evaluation_index: int,
    batch_index: int,
    batch_size: int,
    x: np.ndarray,
) -> Dict[str, Any]:
    record = {
        "evaluation_index": evaluation_index,
        "batch_index": batch_index,
        "batch_size": batch_size,
        "parameter_values": _vector_to_params(x),
        "objective_values": {},
        "status": "pending",
        "failure_reason": None,
        "raw_response": None,
    }
    results.append(record)
    return record


def run_campaign(config: CampaignConfig) -> Dict[str, Any]:
    logfire.info(
        "Starting Ackley 6D campaign",
        case_id=config.case_id,
        total_budget=config.total_budget,
        init_size=config.init_size,
        batch_schedule=config.batch_schedule,
        seed=config.random_seed,
    )
    rng = np.random.default_rng(config.random_seed)
    seen_keys: set[tuple[float, ...]] = set()
    results: List[Dict[str, Any]] = []
    X_obs: List[np.ndarray] = []
    y_obs: List[float] = []

    init_design = latin_hypercube(config.init_size, config.dimensions, rng)
    eval_index = 0

    def evaluate_point(x: np.ndarray, batch_index: int, batch_size: int) -> None:
        nonlocal eval_index
        key = unique_key(x)
        if key in seen_keys:
            raise ValueError("Duplicate evaluation attempted")
        seen_keys.add(key)
        eval_index += 1
        record = _record_attempt(results, eval_index, batch_index, batch_size, x)
        try:
            raw_response, surface_response = evaluate_ackley_6d(record["parameter_values"])
            record["objective_values"] = {config.objective_name: float(surface_response)}
            record["status"] = "success"
            record["raw_response"] = float(raw_response)
            X_obs.append(np.array(x, dtype=float))
            y_obs.append(float(surface_response))
            logfire.info(
                "Evaluation success",
                evaluation_index=eval_index,
                batch_index=batch_index,
                surface_response=float(surface_response),
                raw_response=float(raw_response),
            )
        except Exception as exc:  # pragma: no cover
            record["status"] = "failed"
            record["failure_reason"] = str(exc)
            logfire.info(
                "Evaluation failure",
                evaluation_index=eval_index,
                batch_index=batch_index,
                error=str(exc),
            )

    for x in init_design:
        evaluate_point(x, batch_index=0, batch_size=config.init_size)

    suggestion_config = SuggestionConfig(
        candidate_pool_size=config.candidate_pool_size,
        gp_restarts=config.gp_restarts,
    )

    for bo_iter, batch_size in enumerate(config.batch_schedule, start=1):
        X_arr = np.vstack(X_obs)
        y_arr = np.array(y_obs, dtype=float)
        batch = suggest_batch(X_arr, y_arr, batch_size, rng, seen_keys, suggestion_config)
        for x in batch:
            evaluate_point(np.array(x, dtype=float), batch_index=bo_iter, batch_size=batch_size)

    attempted = len(results)
    successful = sum(r["status"] == "success" for r in results)
    failed = attempted - successful
    if attempted != config.total_budget:
        raise RuntimeError(f"Expected {config.total_budget} attempts, observed {attempted}")
    if successful == 0:
        raise RuntimeError("No successful evaluations")

    success_rows = [r for r in results if r["status"] == "success"]
    best_row = max(success_rows, key=lambda r: r["objective_values"][config.objective_name])

    payload: Dict[str, Any] = {
        "case_id": config.case_id,
        "cache_buster_nonce": "3d4bb0a3-149f-4c0e-abd3-ab2bb235913e",
        "generated_at": datetime.now(UTC).isoformat(),
        "objective_name": config.objective_name,
        "objective_direction": config.objective_direction,
        "objective_unit": config.objective_unit,
        "attempted_evaluations": attempted,
        "successful_evaluations": successful,
        "failed_evaluations": failed,
        "completed_evaluations": successful,
        "best_objective_value": best_row["objective_values"][config.objective_name],
        "best_parameters": best_row["parameter_values"],
        "best_raw_response": best_row["raw_response"],
        "settings": asdict(config),
        "results": results,
    }

    results_path = Path(config.results_path)
    results_path.write_text(json.dumps(payload, indent=2))
    manifest = {
        "package_modules": [
            "ackley6d_campaign.__init__",
            "ackley6d_campaign.objective",
            "ackley6d_campaign.bo",
            "ackley6d_campaign.campaign",
        ],
        "run_entrypoint": "run_ackley6d_campaign.py",
        "latest_local_results": str(results_path),
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2))
    logfire.info(
        "Campaign complete",
        attempted=attempted,
        successful=successful,
        best_objective=payload["best_objective_value"],
        best_raw_response=payload["best_raw_response"],
    )
    return payload
