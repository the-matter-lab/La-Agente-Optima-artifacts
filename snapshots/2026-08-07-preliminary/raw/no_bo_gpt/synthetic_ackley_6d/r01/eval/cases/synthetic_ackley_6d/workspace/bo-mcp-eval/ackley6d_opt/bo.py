from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np
from scipy.stats import norm, qmc
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
import warnings


@dataclass
class CandidateSuggestion:
    x: List[float]
    source: str
    acquisition_value: float | None = None


class LocalBayesOptimizer:
    def __init__(
        self,
        dim: int,
        seed: int,
        initial_design_size: int,
        candidate_pool_size: int = 8192,
        jitter: float = 0.01,
    ) -> None:
        self.dim = dim
        self.seed = seed
        self.initial_design_size = initial_design_size
        self.candidate_pool_size = candidate_pool_size
        self.jitter = jitter
        self._seen: set[tuple[float, ...]] = set()
        self._sobol_seed = seed
        self._rng = np.random.default_rng(seed)

    @staticmethod
    def _key(x: Sequence[float]) -> tuple[float, ...]:
        return tuple(float(f"{v:.12f}") for v in x)

    def register(self, x: Sequence[float]) -> None:
        self._seen.add(self._key(x))

    def has_seen(self, x: Sequence[float]) -> bool:
        return self._key(x) in self._seen

    def _sobol_points(self, n: int, seed_offset: int) -> np.ndarray:
        engine = qmc.Sobol(d=self.dim, scramble=True, seed=self._sobol_seed + seed_offset)
        m = int(np.ceil(np.log2(max(1, n))))
        return engine.random_base2(m=m)[:n]

    def initial_design(self) -> List[CandidateSuggestion]:
        pts = self._sobol_points(self.initial_design_size * 4, seed_offset=0)
        out: List[CandidateSuggestion] = []
        for row in pts:
            x = row.tolist()
            if self.has_seen(x):
                continue
            self.register(x)
            out.append(CandidateSuggestion(x=x, source="sobol_initial"))
            if len(out) >= self.initial_design_size:
                break
        if len(out) != self.initial_design_size:
            raise RuntimeError("Unable to generate unique initial design points.")
        return out

    def _fit_gp(self, xs: np.ndarray, ys: np.ndarray) -> GaussianProcessRegressor:
        kernel = (
            ConstantKernel(1.0, (0.1, 10.0))
            * Matern(length_scale=np.full(self.dim, 0.2), length_scale_bounds=(1e-3, 10.0), nu=2.5)
            + WhiteKernel(noise_level=1e-8, noise_level_bounds=(1e-12, 1e-4))
        )
        gp = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-10,
            normalize_y=True,
            n_restarts_optimizer=4,
            random_state=self.seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            gp.fit(xs, ys)
        return gp

    def _expected_improvement(
        self,
        mu: np.ndarray,
        sigma: np.ndarray,
        best_y: float,
    ) -> np.ndarray:
        sigma = np.maximum(sigma, 1e-12)
        improvement = mu - best_y - self.jitter
        z = improvement / sigma
        return improvement * norm.cdf(z) + sigma * norm.pdf(z)

    def suggest(self, completed_x: Iterable[Sequence[float]], completed_y: Sequence[float]) -> CandidateSuggestion:
        xs = np.asarray(list(completed_x), dtype=float)
        ys = np.asarray(completed_y, dtype=float)
        if xs.shape[0] < 2:
            raise RuntimeError("At least two completed observations are required for BO suggestion.")

        gp = self._fit_gp(xs, ys)
        best_y = float(np.max(ys))

        pool = self._sobol_points(self.candidate_pool_size, seed_offset=int(xs.shape[0]) + 1)
        pool = np.asarray([row for row in pool if not self.has_seen(row)], dtype=float)
        if pool.size == 0:
            raise RuntimeError("Candidate pool exhausted before reaching budget.")

        mu, sigma = gp.predict(pool, return_std=True)
        ei = self._expected_improvement(mu, sigma, best_y)
        order = np.argsort(-ei)
        for idx in order:
            x = pool[idx].tolist()
            if self.has_seen(x):
                continue
            self.register(x)
            return CandidateSuggestion(x=x, source="gp_expected_improvement", acquisition_value=float(ei[idx]))

        raise RuntimeError("Failed to find a unique BO suggestion.")
