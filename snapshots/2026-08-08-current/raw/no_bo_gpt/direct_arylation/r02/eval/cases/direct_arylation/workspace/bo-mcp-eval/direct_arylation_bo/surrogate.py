from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from .search_space import SearchSpace


@dataclass
class SuggestionEngine:
    seed: int = 0
    n_estimators: int = 256
    top_k_sample: int = 12

    def _fit_model(self, X: np.ndarray, y: np.ndarray) -> RandomForestRegressor:
        model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.seed,
            n_jobs=-1,
            bootstrap=True,
            max_features="sqrt",
            min_samples_leaf=1,
        )
        model.fit(X, y)
        return model

    def suggest(
        self,
        observed_candidates: Sequence[Dict[str, object]],
        observed_values: Sequence[float],
        remaining_candidates: Sequence[Dict[str, object]],
        batch_size: int,
        rng: np.random.Generator,
        space: SearchSpace,
    ) -> List[Dict[str, object]]:
        if len(remaining_candidates) <= batch_size:
            return list(remaining_candidates)
        if len(observed_values) < 5:
            idxs = rng.choice(len(remaining_candidates), size=batch_size, replace=False)
            return [remaining_candidates[i] for i in idxs]

        X_obs = np.array([space.encode(c) for c in observed_candidates], dtype=float)
        y_obs = np.array(observed_values, dtype=float)
        X_rem = np.array([space.encode(c) for c in remaining_candidates], dtype=float)
        model = self._fit_model(X_obs, y_obs)
        tree_preds = np.stack([tree.predict(X_rem) for tree in model.estimators_], axis=0)
        mean = tree_preds.mean(axis=0)
        std = tree_preds.std(axis=0)
        best = float(np.max(y_obs))
        xi = max(0.01, 0.05 * float(np.std(y_obs)))
        ei = self.expected_improvement(mean, std, best, xi)
        jitter = rng.uniform(0.0, 1e-9, size=ei.shape[0])
        ranked = np.argsort(-(ei + jitter))
        top_pool = ranked[: min(self.top_k_sample, ranked.shape[0])]
        chosen: List[int] = []
        pool = list(top_pool)
        while len(chosen) < batch_size and pool:
            scores = np.array([ei[i] for i in pool], dtype=float)
            weights = np.exp((scores - scores.max()) / max(scores.std(), 1e-6))
            weights = weights / weights.sum()
            pick = int(rng.choice(pool, p=weights))
            chosen.append(pick)
            pool = [i for i in pool if i != pick]
        if len(chosen) < batch_size:
            for idx in ranked:
                if int(idx) not in chosen:
                    chosen.append(int(idx))
                if len(chosen) == batch_size:
                    break
        return [remaining_candidates[i] for i in chosen]

    @staticmethod
    def expected_improvement(mean: np.ndarray, std: np.ndarray, best: float, xi: float) -> np.ndarray:
        out = np.zeros_like(mean, dtype=float)
        positive = std > 1e-12
        if not np.any(positive):
            return out
        imp = mean[positive] - best - xi
        z = imp / std[positive]
        phi = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
        Phi = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
        out[positive] = imp * Phi + std[positive] * phi
        return out
