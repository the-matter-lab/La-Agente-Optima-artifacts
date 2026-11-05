from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from .search_space import Candidate, encode_candidates, sample_unique_candidates

try:
    from sklearn.ensemble import RandomForestRegressor
except Exception:  # pragma: no cover
    RandomForestRegressor = None


@dataclass
class Suggestion:
    candidate: Candidate
    strategy: str
    acquisition: float | None = None


class SurrogateBO:
    def __init__(self, seed: int, init_random: int = 12, pool_size: int = 512, explore_prob: float = 0.12):
        self.seed = seed
        self.init_random = init_random
        self.pool_size = pool_size
        self.explore_prob = explore_prob
        self.rng = random.Random(seed)

    def suggest(self, observed_candidates: Sequence[Candidate], observed_yields: Sequence[float], seen_keys: set[tuple]) -> Suggestion:
        if len(observed_candidates) < self.init_random or len(observed_yields) < max(4, self.init_random // 2):
            cand = sample_unique_candidates(self.rng, 1, seen_keys)[0]
            return Suggestion(candidate=cand, strategy='random_initial')

        if self.rng.random() < self.explore_prob:
            cand = sample_unique_candidates(self.rng, 1, seen_keys)[0]
            return Suggestion(candidate=cand, strategy='random_exploration')

        pool = sample_unique_candidates(self.rng, self.pool_size, seen_keys)
        if not pool:
            raise RuntimeError('No unseen candidates remain in the search space.')
        x_train = np.asarray(encode_candidates(observed_candidates), dtype=float)
        y_train = np.asarray(observed_yields, dtype=float)
        x_pool = np.asarray(encode_candidates(pool), dtype=float)
        means, stds = self._predict_mean_std(x_train, y_train, x_pool)
        best_y = float(np.max(y_train))
        eis = np.array([self._expected_improvement(m, s, best_y) for m, s in zip(means, stds)])
        best_idx = int(np.argmax(eis))
        return Suggestion(candidate=pool[best_idx], strategy='model_guided_ei', acquisition=float(eis[best_idx]))

    def _predict_mean_std(self, x_train: np.ndarray, y_train: np.ndarray, x_pool: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if RandomForestRegressor is not None:
            model = RandomForestRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                random_state=self.seed + len(y_train),
                n_jobs=1,
            )
            model.fit(x_train, y_train)
            tree_preds = np.stack([tree.predict(x_pool) for tree in model.estimators_], axis=0)
            means = np.mean(tree_preds, axis=0)
            stds = np.std(tree_preds, axis=0, ddof=1)
            stds = np.maximum(stds, 1e-6)
            return means, stds

        means = []
        stds = []
        for row in x_pool:
            dists = np.sqrt(np.sum((x_train - row) ** 2, axis=1))
            idx = np.argsort(dists)[: min(8, len(dists))]
            nbrs = y_train[idx]
            weights = 1.0 / np.maximum(dists[idx], 0.2)
            mean = float(np.average(nbrs, weights=weights))
            var = float(np.average((nbrs - mean) ** 2, weights=weights))
            means.append(mean)
            stds.append(max(math.sqrt(var), 1e-3))
        return np.asarray(means), np.asarray(stds)

    @staticmethod
    def _normal_pdf(z: float) -> float:
        return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)

    @staticmethod
    def _normal_cdf(z: float) -> float:
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    def _expected_improvement(self, mean: float, std: float, best: float) -> float:
        if std <= 1e-12:
            return max(0.0, mean - best)
        z = (mean - best) / std
        return (mean - best) * self._normal_cdf(z) + std * self._normal_pdf(z)
