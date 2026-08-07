from __future__ import annotations

from dataclasses import dataclass
from math import erf, pi, sqrt
from typing import Iterable, List, Sequence, Tuple

import numpy as np
from scipy.stats import qmc
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel


@dataclass
class CandidateSuggestion:
    x: np.ndarray
    acquisition_value: float
    stage: str


class LocalGaussianProcessBO:
    def __init__(
        self,
        dim: int,
        bounds: Sequence[Tuple[float, float]],
        seed: int,
        init_size: int,
        acquisition_samples: int = 4096,
    ) -> None:
        self.dim = dim
        self.bounds = np.array(bounds, dtype=float)
        self.seed = seed
        self.init_size = init_size
        self.acquisition_samples = acquisition_samples
        self.rng = np.random.default_rng(seed)
        self._lhs_engine = qmc.LatinHypercube(d=dim, seed=seed)
        kernel = (
            ConstantKernel(1.0, constant_value_bounds="fixed")
            * Matern(length_scale=np.full(dim, 0.2), length_scale_bounds="fixed", nu=2.5)
            + WhiteKernel(noise_level=1e-8, noise_level_bounds="fixed")
        )
        self.model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=0.0,
            normalize_y=True,
            optimizer=None,
            random_state=seed,
        )

    @staticmethod
    def key_for(x: np.ndarray) -> Tuple[float, ...]:
        return tuple(np.round(np.asarray(x, dtype=float), 12).tolist())

    def initial_design(self, seen: Iterable[Tuple[float, ...]], n_points: int) -> List[CandidateSuggestion]:
        seen_keys = set(seen)
        suggestions: List[CandidateSuggestion] = []
        while len(suggestions) < n_points:
            draws = self._lhs_engine.random(n=max(8, n_points * 2))
            for row in draws:
                x = self._scale_to_bounds(row)
                key = self.key_for(x)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                suggestions.append(CandidateSuggestion(x=x, acquisition_value=float("nan"), stage="initial"))
                if len(suggestions) >= n_points:
                    break
        return suggestions

    def suggest(self, X: np.ndarray, y: np.ndarray, seen: Iterable[Tuple[float, ...]]) -> CandidateSuggestion:
        seen_keys = set(seen)
        if len(X) < self.init_size:
            return self.initial_design(seen_keys, 1)[0]

        self.model.fit(X, y)
        incumbent = X[int(np.argmax(y))]
        candidates = self._sample_candidate_pool(seen_keys, incumbent=incumbent, n_obs=len(X))
        mu, std = self.model.predict(candidates, return_std=True)
        best_y = float(np.max(y))
        ei = self._expected_improvement(mu, std, best_y)
        best_idx = int(np.argmax(ei))
        return CandidateSuggestion(
            x=candidates[best_idx],
            acquisition_value=float(ei[best_idx]),
            stage="bayesopt",
        )

    def _sample_candidate_pool(
        self,
        seen: set[Tuple[float, ...]],
        incumbent: np.ndarray,
        n_obs: int,
    ) -> np.ndarray:
        global_target = self.acquisition_samples // 2
        local_target = self.acquisition_samples - global_target
        pool: List[np.ndarray] = []

        while len(pool) < global_target:
            sample = self.rng.uniform(self.bounds[:, 0], self.bounds[:, 1], size=(global_target, self.dim))
            for row in sample:
                key = self.key_for(row)
                if key in seen:
                    continue
                seen.add(key)
                pool.append(row)
                if len(pool) >= global_target:
                    break

        sigma = max(0.03, 0.18 * (0.97 ** max(n_obs - self.init_size, 0)))
        while len(pool) < self.acquisition_samples:
            sample = self.rng.normal(loc=incumbent, scale=sigma, size=(local_target, self.dim))
            sample = np.clip(sample, self.bounds[:, 0], self.bounds[:, 1])
            for row in sample:
                key = self.key_for(row)
                if key in seen:
                    continue
                seen.add(key)
                pool.append(row)
                if len(pool) >= self.acquisition_samples:
                    break

        return np.asarray(pool, dtype=float)

    @staticmethod
    def _expected_improvement(mu: np.ndarray, std: np.ndarray, best_y: float) -> np.ndarray:
        std = np.maximum(std, 1e-12)
        improvement = mu - best_y
        z = improvement / std
        normal_pdf = np.exp(-0.5 * z * z) / sqrt(2.0 * pi)
        normal_cdf = 0.5 * (1.0 + np.vectorize(erf)(z / sqrt(2.0)))
        return improvement * normal_cdf + std * normal_pdf

    def _scale_to_bounds(self, unit_points: np.ndarray) -> np.ndarray:
        return self.bounds[:, 0] + unit_points * (self.bounds[:, 1] - self.bounds[:, 0])
