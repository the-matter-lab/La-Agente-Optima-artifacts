from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .space import Candidate, OneHotInteractionEncoder, candidate_key, sample_random_candidates


@dataclass
class BayesianLinearThompsonConfig:
    alpha: float = 2.0
    beta: float = 15.0
    pool_size: int = 256
    jitter: float = 1e-8


class BayesianLinearThompson:
    def __init__(
        self,
        encoder: OneHotInteractionEncoder,
        rng: np.random.Generator,
        config: BayesianLinearThompsonConfig | None = None,
    ) -> None:
        self.encoder = encoder
        self.rng = rng
        self.config = config or BayesianLinearThompsonConfig()
        self._posterior_mean: np.ndarray | None = None
        self._precision_cholesky: np.ndarray | None = None
        self._y_mean = 0.0
        self._y_scale = 1.0

    def fit(self, candidates: list[Candidate], objective_values: list[float]) -> None:
        if not candidates:
            self._posterior_mean = None
            self._precision_cholesky = None
            self._y_mean = 0.0
            self._y_scale = 1.0
            return
        x = self.encoder.encode(candidates)
        y = np.asarray(objective_values, dtype=float)
        self._y_mean = float(np.mean(y))
        self._y_scale = float(np.std(y))
        if self._y_scale < 1e-6:
            self._y_scale = 1.0
        y_std = (y - self._y_mean) / self._y_scale
        n_features = x.shape[1]
        precision = self.config.alpha * np.eye(n_features) + self.config.beta * (x.T @ x)
        precision = 0.5 * (precision + precision.T)
        rhs = self.config.beta * x.T @ y_std
        for attempt in range(6):
            jitter = self.config.jitter * (10**attempt)
            try:
                stabilized = precision + jitter * np.eye(n_features)
                cholesky = np.linalg.cholesky(stabilized)
                mean = np.linalg.solve(stabilized, rhs)
                self._precision_cholesky = cholesky
                self._posterior_mean = mean
                return
            except np.linalg.LinAlgError:
                continue
        raise np.linalg.LinAlgError("Unable to stabilize Bayesian linear posterior precision.")

    def predict_mean(self, candidates: list[Candidate]) -> np.ndarray:
        if not candidates:
            return np.array([], dtype=float)
        if self._posterior_mean is None:
            return np.zeros(len(candidates), dtype=float)
        x = self.encoder.encode(candidates)
        return (x @ self._posterior_mean) * self._y_scale + self._y_mean

    def sample_scores(self, candidates: list[Candidate]) -> np.ndarray:
        if not candidates:
            return np.array([], dtype=float)
        if self._posterior_mean is None or self._precision_cholesky is None:
            return self.rng.normal(size=len(candidates))
        x = self.encoder.encode(candidates)
        noise = self.rng.normal(size=self._posterior_mean.shape[0])
        sampled_delta = np.linalg.solve(self._precision_cholesky.T, noise)
        sampled_weights = self._posterior_mean + sampled_delta
        return (x @ sampled_weights) * self._y_scale + self._y_mean

    def suggest_batch(
        self,
        seen_keys: set[tuple[Any, ...]],
        batch_size: int,
    ) -> list[Candidate]:
        selected: list[Candidate] = []
        blocked = set(seen_keys)
        for _ in range(batch_size):
            pool = sample_random_candidates(
                rng=self.rng,
                n=self.config.pool_size,
                exclude=blocked,
            )
            scores = self.sample_scores(pool)
            means = self.predict_mean(pool)
            blended = 0.65 * scores + 0.35 * means
            best_idx = int(np.argmax(blended))
            best_candidate = pool[best_idx]
            selected.append(best_candidate)
            blocked.add(candidate_key(best_candidate))
        return selected
