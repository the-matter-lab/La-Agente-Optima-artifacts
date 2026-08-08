from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import logfire
    from grafico.core.logfire_config import configure_logfire

    configure_logfire()
    logfire.instrument_requests()
except Exception:  # pragma: no cover
    class _LogfireFallback:
        @staticmethod
        def info(msg: str, **kwargs: Any) -> None:
            return None

        @staticmethod
        def debug(msg: str, **kwargs: Any) -> None:
            return None

    logfire = _LogfireFallback()

from .bo import Candidate, CandidateEncoder, choose_next_candidate, full_search_space
from .oracle import DirectArylationOracle, api_url_from_env


CASE_ID = "direct_arylation_reaction_yield_optimization"
OBJECTIVE_NAME = "yield"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "percent"


@dataclass
class CampaignConfig:
    budget: int = 60
    n_initial: int = 12
    seed: int = 20260730
    dry_run: bool = False
    output_path: str = "local_results.json"
    manifest_path: str = "campaign_manifest.json"
    cache_buster_nonce: str = ""


@dataclass
class AttemptRecord:
    evaluation_index: int
    batch_index: int
    batch_size: int
    parameter_values: dict[str, Any]
    status: str
    objective_values: dict[str, float] | None = None
    failure_reason: str | None = None


def _candidate_digest(candidate: Candidate) -> str:
    payload = json.dumps(candidate.to_parameter_values(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_campaign(config: CampaignConfig) -> dict[str, Any]:
    if config.budget <= 0:
        raise ValueError("budget must be positive")
    if config.n_initial <= 0:
        raise ValueError("n_initial must be positive")
    if config.n_initial >= config.budget:
        raise ValueError("n_initial must be smaller than budget to allow BO iterations")

    rng_seed = int(config.seed)
    logfire.info("starting_direct_arylation_campaign", budget=config.budget, seed=rng_seed, dry_run=config.dry_run)

    import numpy as np

    rng = np.random.default_rng(rng_seed)
    encoder = CandidateEncoder()
    oracle = DirectArylationOracle(api_url=api_url_from_env(), dry_run=config.dry_run)
    search_space = full_search_space()
    remaining = list(search_space)
    attempts: list[AttemptRecord] = []
    successful_candidates: list[Candidate] = []
    successful_yields: list[float] = []

    initial_indices = rng.choice(len(remaining), size=config.n_initial, replace=False)
    initial_candidates = [remaining[i] for i in sorted(initial_indices, reverse=True)]
    for candidate in initial_candidates:
        remaining.remove(candidate)

    bo_iteration = 0
    for idx in range(1, config.budget + 1):
        if idx <= config.n_initial:
            candidate = initial_candidates[config.n_initial - idx]
        else:
            bo_iteration += 1
            candidate = choose_next_candidate(
                rng=rng,
                encoder=encoder,
                observed_candidates=successful_candidates,
                observed_yields=successful_yields,
                remaining_candidates=remaining,
                iteration_index=bo_iteration,
            )
            remaining.remove(candidate)

        result = oracle.evaluate(candidate)
        record = AttemptRecord(
            evaluation_index=idx,
            batch_index=idx,
            batch_size=1,
            parameter_values=candidate.to_parameter_values(),
            status=result.status,
            objective_values=result.objective_values,
            failure_reason=result.failure_reason,
        )
        attempts.append(record)

        digest = _candidate_digest(candidate)
        if result.status == "success" and result.objective_values is not None:
            measured_yield = float(result.objective_values[OBJECTIVE_NAME])
            successful_candidates.append(candidate)
            successful_yields.append(measured_yield)
            print(
                f"[{idx:02d}/{config.budget}] success yield={measured_yield:6.2f}% "
                f"base={candidate.base}; ligand={candidate.ligand}; solvent={candidate.solvent}; "
                f"concentration={candidate.concentration}; temperature_c={candidate.temperature_c}"
            )
            logfire.info("objective_success", evaluation_index=idx, candidate_id=digest, measured_yield=measured_yield)
        else:
            print(
                f"[{idx:02d}/{config.budget}] failed reason={result.failure_reason} "
                f"base={candidate.base}; ligand={candidate.ligand}; solvent={candidate.solvent}; "
                f"concentration={candidate.concentration}; temperature_c={candidate.temperature_c}"
            )
            logfire.info("objective_failure", evaluation_index=idx, candidate_id=digest, reason=result.failure_reason)

    best_idx = None
    best_value = None
    for i, value in enumerate(successful_yields):
        if best_value is None or value > best_value:
            best_value = value
            best_idx = i

    best_parameters = successful_candidates[best_idx].to_parameter_values() if best_idx is not None else None
    ordered_results: list[dict[str, Any]] = [asdict(record) for record in attempts]
    summary = {
        "case_id": CASE_ID,
        "cache_buster_nonce": config.cache_buster_nonce,
        "objective_name": OBJECTIVE_NAME,
        "objective_direction": OBJECTIVE_DIRECTION,
        "objective_unit": OBJECTIVE_UNIT,
        "attempted_evaluations": len(attempts),
        "completed_evaluations": len(successful_yields),
        "failed_evaluations": len(attempts) - len(successful_yields),
        "best_objective_value": best_value,
        "best_parameters": best_parameters,
        "results": ordered_results,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "config": asdict(config),
    }
    _write_json(config.output_path, summary)
    manifest = {
        "package_modules": [
            "direct_arylation_campaign.__init__",
            "direct_arylation_campaign.bo",
            "direct_arylation_campaign.oracle",
            "direct_arylation_campaign.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_campaign.py",
        "latest_local_results": str(Path(config.output_path).resolve()),
    }
    _write_json(config.manifest_path, manifest)

    print(
        "Campaign complete: "
        f"attempted={summary['attempted_evaluations']} successful={summary['completed_evaluations']} "
        f"best_yield={summary['best_objective_value']}"
    )
    return summary
