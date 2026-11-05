from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern

from .objective import PARAMETER_NAMES


@dataclass
class BOConfig:
    seed: int = 20260812
    dimensions: int = 6
    initial_design_size: int = 12
    candidate_pool_size: int = 4096
    jitter: float = 0.01
    gp_restarts: int = 3


class LocalBayesOptimizer:
    def __init__(self, config: BOConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)

    @staticmethod
    def _key_from_array(x: np.ndarray) -> Tuple[float, ...]:
        return tuple(np.round(np.asarray(x, dtype=float), 12).tolist())

    def seen_keys(self, results: Sequence[Dict]) -> Set[Tuple[float, ...]]:
        keys: Set[Tuple[float, ...]] = set()
        for row in results:
            params = row["parameter_values"]
            arr = np.array([params[name] for name in PARAMETER_NAMES], dtype=float)
            keys.add(self._key_from_array(arr))
        return keys

    def random_unique_point(self, seen: Set[Tuple[float, ...]]) -> np.ndarray:
        while True:
            x = self.rng.uniform(0.0, 1.0, size=self.config.dimensions)
            key = self._key_from_array(x)
            if key not in seen:
                seen.add(key)
                return x

    def _fit_gp(self, X: np.ndarray, y: np.ndarray) -> GaussianProcessRegressor:
        kernel = ConstantKernel(1.0, (0.1, 10.0)) * Matern(
            length_scale=np.full(self.config.dimensions, 0.2),
            length_scale_bounds=(1e-2, 10.0),
            nu=2.5,
        )
        model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-10,
            normalize_y=True,
            n_restarts_optimizer=self.config.gp_restarts,
            random_state=self.config.seed,
        )
        model.fit(X, y)
        return model

    def _expected_improvement(
        self,
        model: GaussianProcessRegressor,
        Xcand: np.ndarray,
        best_y: float,
    ) -> np.ndarray:
        mu, sigma = model.predict(Xcand, return_std=True)
        sigma = np.maximum(sigma, 1e-12)
        improvement = mu - best_y - self.config.jitter
        z = improvement / sigma
        ei = improvement * norm.cdf(z) + sigma * norm.pdf(z)
        ei[sigma <= 1e-12] = 0.0
        return ei

    def _unique_candidate_pool(self, seen: Set[Tuple[float, ...]]) -> np.ndarray:
        pool: List[np.ndarray] = []
        local_seen = set(seen)
        while len(pool) < self.config.candidate_pool_size:
            x = self.rng.uniform(0.0, 1.0, size=self.config.dimensions)
            key = self._key_from_array(x)
            if key not in local_seen:
                local_seen.add(key)
                pool.append(x)
        return np.vstack(pool)

    def suggest(self, results: Sequence[Dict]) -> Dict[str, float]:
        seen = self.seen_keys(results)
        if len(results) < self.config.initial_design_size:
            x = self.random_unique_point(seen)
        else:
            X = np.array(
                [
                    [row["parameter_values"][name] for name in PARAMETER_NAMES]
                    for row in results
                    if row["status"] == "success"
                ],
                dtype=float,
            )
            y = np.array(
                [
                    row["objective_values"]["surface_response"]
                    for row in results
                    if row["status"] == "success"
                ],
                dtype=float,
            )
            if len(y) < max(3, self.config.dimensions):
                x = self.random_unique_point(seen)
            else:
                model = self._fit_gp(X, y)
                pool = self._unique_candidate_pool(seen)
                ei = self._expected_improvement(model, pool, float(np.max(y)))
                best_idx = int(np.argmax(ei))
                if float(ei[best_idx]) <= 0.0:
                    mu = model.predict(pool)
                    best_idx = int(np.argmax(mu))
                x = pool[best_idx]
        return {name: float(value) for name, value in zip(PARAMETER_NAMES, x)}
