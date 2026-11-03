from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
from sklearn.exceptions import ConvergenceWarning

try:
    import logfire
except Exception:  # pragma: no cover
    class _NoopLogfire:
        def instrument_requests(self):
            return None
        def info(self, *args, **kwargs):
            return None
        def debug(self, *args, **kwargs):
            return None
    logfire = _NoopLogfire()

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # pragma: no cover
    def configure_logfire():
        return None
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
import warnings

configure_logfire()
logfire.instrument_requests()

CASE_ID = "synthetic_ackley_6d"
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "normalized_unitless"
DIMENSION = 6
PARAMETER_NAMES = [f"x_{i}" for i in range(1, DIMENSION + 1)]
LOWER_BOUNDS = np.zeros(DIMENSION)
UPPER_BOUNDS = np.ones(DIMENSION)
ACKLEY_RAW_MIN = -22.350402387287602
ACKLEY_RAW_MAX = 0.0


@dataclass(frozen=True)
class CampaignConfig:
    seed: int = 20260812
    total_budget: int = 60
    init_size: int = 12
    guided_batch_size: int = 4
    acquisition_pool_size: int = 4096
    duplicate_round_decimals: int = 12

    @property
    def n_guided(self) -> int:
        return self.total_budget - self.init_size

    @property
    def n_guided_batches(self) -> int:
        if self.n_guided % self.guided_batch_size != 0:
            raise ValueError("guided budget must be divisible by guided batch size")
        return self.n_guided // self.guided_batch_size


class AckleySurface:
    @staticmethod
    def normalized_to_z(x: np.ndarray) -> np.ndarray:
        return -40.0 + 80.0 * x

    @classmethod
    def evaluate(cls, x: np.ndarray) -> Tuple[float, float]:
        z = cls.normalized_to_z(x)
        d = float(len(z))
        classic = (
            -20.0 * math.exp(-0.2 * math.sqrt(float(np.sum(z ** 2)) / d))
            - math.exp(float(np.sum(np.cos(2.0 * math.pi * z))) / d)
            + 20.0
            + math.e
        )
        raw_response = -classic
        surface_response = (raw_response - ACKLEY_RAW_MIN) / (ACKLEY_RAW_MAX - ACKLEY_RAW_MIN)
        return raw_response, surface_response


class GaussianProcessBatchBO:
    def __init__(self, config: CampaignConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.random = random.Random(config.seed)
        self.seen: set[Tuple[float, ...]] = set()
        self.kernel = (
            ConstantKernel(1.0, (1e-3, 1e3))
            * Matern(length_scale=np.full(DIMENSION, 0.2), length_scale_bounds=(1e-3, 10.0), nu=2.5)
            + WhiteKernel(noise_level=1e-8, noise_level_bounds=(1e-12, 1e-4))
        )

    def _key(self, x: Sequence[float]) -> Tuple[float, ...]:
        return tuple(round(float(v), self.config.duplicate_round_decimals) for v in x)

    def _register(self, x: np.ndarray) -> None:
        key = self._key(x)
        if key in self.seen:
            raise ValueError(f"duplicate point detected: {key}")
        self.seen.add(key)

    def random_unique_points(self, n: int) -> np.ndarray:
        points: List[np.ndarray] = []
        while len(points) < n:
            x = self.rng.uniform(LOWER_BOUNDS, UPPER_BOUNDS)
            key = self._key(x)
            if key in self.seen:
                continue
            self.seen.add(key)
            points.append(x)
        return np.vstack(points)

    @staticmethod
    def _norm_pdf(z: np.ndarray) -> np.ndarray:
        return np.exp(-0.5 * z ** 2) / math.sqrt(2.0 * math.pi)

    @staticmethod
    def _norm_cdf(z: np.ndarray) -> np.ndarray:
        return 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))

    def _fit_gp(self, xs: np.ndarray, ys: np.ndarray) -> GaussianProcessRegressor:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            gp = GaussianProcessRegressor(
                kernel=self.kernel,
                normalize_y=True,
                n_restarts_optimizer=3,
                random_state=self.config.seed,
                alpha=1e-10,
            )
            gp.fit(xs, ys)
        return gp

    def _sample_pool(self, pending_keys: set[Tuple[float, ...]]) -> np.ndarray:
        pool: List[np.ndarray] = []
        local_seen = set(pending_keys)
        while len(pool) < self.config.acquisition_pool_size:
            x = self.rng.uniform(LOWER_BOUNDS, UPPER_BOUNDS)
            key = self._key(x)
            if key in self.seen or key in local_seen:
                continue
            local_seen.add(key)
            pool.append(x)
        return np.vstack(pool)

    def _expected_improvement(self, mean: np.ndarray, sigma: np.ndarray, best_y: float, xi: float = 0.01) -> np.ndarray:
        improvement = mean - best_y - xi
        safe_sigma = np.maximum(sigma, 1e-12)
        z = improvement / safe_sigma
        ei = improvement * self._norm_cdf(z) + safe_sigma * self._norm_pdf(z)
        ei[sigma < 1e-12] = 0.0
        return ei

    def suggest_batch(self, xs: np.ndarray, ys: np.ndarray, batch_size: int) -> np.ndarray:
        gp = self._fit_gp(xs, ys)
        pending: List[np.ndarray] = []
        pending_keys: set[Tuple[float, ...]] = set()
        fantasy_xs = xs.copy()
        fantasy_ys = ys.copy()
        for _ in range(batch_size):
            pool = self._sample_pool(pending_keys)
            mean, sigma = gp.predict(pool, return_std=True)
            ei = self._expected_improvement(mean, sigma, float(np.max(fantasy_ys)))
            best_idx = int(np.argmax(ei))
            candidate = pool[best_idx]
            key = self._key(candidate)
            pending.append(candidate)
            pending_keys.add(key)
            pred_mean = float(mean[best_idx])
            fantasy_xs = np.vstack([fantasy_xs, candidate])
            fantasy_ys = np.append(fantasy_ys, pred_mean)
            gp = self._fit_gp(fantasy_xs, fantasy_ys)
        batch = np.vstack(pending)
        for candidate in batch:
            self._register(candidate)
        return batch


def _serialize_float(value: float) -> float:
    return float(f"{float(value):.16g}")


def _record_result(
    *,
    evaluation_index: int,
    batch_index: int,
    batch_size: int,
    x: np.ndarray,
    raw_response: float,
    surface_response: float,
) -> Dict[str, object]:
    return {
        "evaluation_index": evaluation_index,
        "batch_index": batch_index,
        "batch_size": batch_size,
        "parameter_values": {name: _serialize_float(val) for name, val in zip(PARAMETER_NAMES, x)},
        "objective_values": {OBJECTIVE_NAME: _serialize_float(surface_response)},
        "status": "success",
        "failure_reason": None,
        "raw_response": _serialize_float(raw_response),
        "objective_unit": OBJECTIVE_UNIT,
    }


def _best_success(results: Sequence[Dict[str, object]]) -> Dict[str, object]:
    successful = [r for r in results if r["status"] == "success"]
    if not successful:
        raise ValueError("no successful evaluations recorded")
    return max(successful, key=lambda r: float(r["objective_values"][OBJECTIVE_NAME]))


def _write_manifest(package_dir: Path, entrypoint: Path, output_path: Path) -> None:
    manifest = {
        "package_modules": [
            str(package_dir / "__init__.py"),
            str(package_dir / "campaign.py"),
        ],
        "run_entrypoint": str(entrypoint),
        "latest_local_results": str(output_path),
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def preflight(config: CampaignConfig | None = None) -> Dict[str, object]:
    config = config or CampaignConfig()
    guided_total = config.n_guided_batches * config.guided_batch_size
    if config.init_size + guided_total != config.total_budget:
        raise ValueError("budget schedule does not sum to total budget")
    info = {
        "case_id": CASE_ID,
        "seed": config.seed,
        "dimensions": DIMENSION,
        "bounds": {name: [0.0, 1.0] for name in PARAMETER_NAMES},
        "objective_name": OBJECTIVE_NAME,
        "objective_direction": OBJECTIVE_DIRECTION,
        "objective_unit": OBJECTIVE_UNIT,
        "total_budget": config.total_budget,
        "init_size": config.init_size,
        "guided_batch_size": config.guided_batch_size,
        "guided_batches": config.n_guided_batches,
        "acquisition": "Gaussian-process expected improvement with greedy constant-liar batching",
        "output_artifact": "local_results.json",
        "entrypoint": "run_ackley6d_surface_opt.py",
        "environment_requirements": ["numpy", "scikit-learn", "logfire", "grafico"],
    }
    logfire.info("Ackley campaign preflight passed", **info)
    return info


def run_campaign(config: CampaignConfig | None = None, output_path: str = "local_results.json") -> Dict[str, object]:
    config = config or CampaignConfig()
    preflight_info = preflight(config)
    bo = GaussianProcessBatchBO(config)
    results: List[Dict[str, object]] = []

    logfire.info("Starting Ackley optimization campaign", seed=config.seed, total_budget=config.total_budget)

    initial_batch = bo.random_unique_points(config.init_size)
    for eval_offset, x in enumerate(initial_batch, start=1):
        raw_response, surface_response = AckleySurface.evaluate(x)
        results.append(
            _record_result(
                evaluation_index=eval_offset,
                batch_index=0,
                batch_size=config.init_size,
                x=x,
                raw_response=raw_response,
                surface_response=surface_response,
            )
        )
    logfire.info(
        "Completed initial design",
        evaluations=len(results),
        best_surface_response=max(float(r["objective_values"][OBJECTIVE_NAME]) for r in results),
    )

    for guided_batch_idx in range(1, config.n_guided_batches + 1):
        xs = np.array([[r["parameter_values"][name] for name in PARAMETER_NAMES] for r in results], dtype=float)
        ys = np.array([r["objective_values"][OBJECTIVE_NAME] for r in results], dtype=float)
        batch = bo.suggest_batch(xs, ys, config.guided_batch_size)
        batch_start = len(results) + 1
        for inner_idx, x in enumerate(batch):
            raw_response, surface_response = AckleySurface.evaluate(x)
            results.append(
                _record_result(
                    evaluation_index=batch_start + inner_idx,
                    batch_index=guided_batch_idx,
                    batch_size=config.guided_batch_size,
                    x=x,
                    raw_response=raw_response,
                    surface_response=surface_response,
                )
            )
        current_best = _best_success(results)
        logfire.info(
            "Completed guided batch",
            batch_index=guided_batch_idx,
            evaluations=len(results),
            best_surface_response=float(current_best["objective_values"][OBJECTIVE_NAME]),
        )

    if len(results) != config.total_budget:
        raise ValueError(f"expected {config.total_budget} results, got {len(results)}")

    best = _best_success(results)
    successful_count = sum(1 for r in results if r["status"] == "success")
    attempted_count = len(results)
    summary = {
        "cache_buster_nonce": "d3d2883c-3b7a-47f6-9edc-5fcf9f429b98",
        "case_id": CASE_ID,
        "objective_name": OBJECTIVE_NAME,
        "objective_direction": OBJECTIVE_DIRECTION,
        "objective_unit": OBJECTIVE_UNIT,
        "completed_evaluations": successful_count,
        "successful_evaluations": successful_count,
        "attempted_evaluations": attempted_count,
        "best_objective_value": _serialize_float(best["objective_values"][OBJECTIVE_NAME]),
        "best_parameters": best["parameter_values"],
        "best_raw_response": _serialize_float(best["raw_response"]),
        "results": results,
        "optimizer": {
            "backend": "local_gaussian_process_bo",
            "random_seed": config.seed,
            "initialization_strategy": "uniform random initial design",
            "initialization_size": config.init_size,
            "guided_batch_size": config.guided_batch_size,
            "guided_batches": config.n_guided_batches,
            "acquisition_strategy": preflight_info["acquisition"],
            "acquisition_pool_size": config.acquisition_pool_size,
        },
    }
    output = Path(output_path)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_manifest(Path("ackley6d_surface_opt"), Path("run_ackley6d_surface_opt.py"), output)
    logfire.info(
        "Ackley campaign finished",
        output_path=str(output),
        best_surface_response=float(best["objective_values"][OBJECTIVE_NAME]),
        attempted_evaluations=attempted_count,
    )
    return summary
