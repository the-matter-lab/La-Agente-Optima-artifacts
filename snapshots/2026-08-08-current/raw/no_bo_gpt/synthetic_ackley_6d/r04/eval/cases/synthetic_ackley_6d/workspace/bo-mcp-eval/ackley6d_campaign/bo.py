from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Set, Tuple

import numpy as np
from scipy.stats import norm, qmc
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
import warnings


@dataclass
class BOConfig:
    dim: int = 6
    budget: int = 60
    init_size: int = 16
    candidate_pool_size: int = 4096
    seed: int = 731245
    ei_xi: float = 0.01


def point_key(x: Sequence[float], decimals: int = 12) -> Tuple[float, ...]:
    arr = np.asarray(x, dtype=float)
    return tuple(np.round(arr, decimals=decimals).tolist())


class LocalBayesOptimizer:
    def __init__(self, config: BOConfig):
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        self.dim = config.dim
        self._sobol = qmc.Sobol(d=self.dim, scramble=True, seed=config.seed)

    def initial_design(self) -> np.ndarray:
        return self._sobol.random_base2(m=int(np.log2(self.config.init_size)))

    def _fit_gp(self, x: np.ndarray, y: np.ndarray) -> GaussianProcessRegressor:
        kernel = (
            ConstantKernel(1.0, (1e-3, 1e3))
            * Matern(length_scale=np.ones(self.dim), length_scale_bounds=(1e-2, 10.0), nu=2.5)
            + WhiteKernel(noise_level=1e-8, noise_level_bounds=(1e-10, 1e-4))
        )
        gp = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-10,
            normalize_y=True,
            n_restarts_optimizer=3,
            random_state=self.config.seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            gp.fit(x, y)
        return gp

    def _sample_unseen_pool(self, seen: Set[Tuple[float, ...]], multiplier: int = 6) -> np.ndarray:
        needed = self.config.candidate_pool_size
        pool: List[np.ndarray] = []
        while len(pool) < needed:
            candidates = self.rng.random((needed * multiplier, self.dim))
            for row in candidates:
                key = point_key(row)
                if key in seen:
                    continue
                pool.append(row)
                if len(pool) >= needed:
                    break
        return np.asarray(pool, dtype=float)

    def _expected_improvement(self, gp: GaussianProcessRegressor, candidates: np.ndarray, y_best: float) -> np.ndarray:
        mu, std = gp.predict(candidates, return_std=True)
        std = np.maximum(std, 1e-12)
        improvement = mu - y_best - self.config.ei_xi
        z = improvement / std
        return improvement * norm.cdf(z) + std * norm.pdf(z)

    def suggest(self, x_obs: np.ndarray, y_obs: np.ndarray, seen: Set[Tuple[float, ...]]) -> np.ndarray:
        if len(x_obs) < self.config.init_size:
            raise ValueError("Need full initial design before BO suggestions")
        try:
            gp = self._fit_gp(x_obs, y_obs)
            pool = self._sample_unseen_pool(seen)
            ei = self._expected_improvement(gp, pool, float(np.max(y_obs)))
            order = np.argsort(ei)[::-1]
            for idx in order:
                candidate = pool[idx]
                if point_key(candidate) not in seen:
                    return candidate
        except Exception:
            pass
        while True:
            candidate = self.rng.random(self.dim)
            if point_key(candidate) not in seen:
                return candidate
