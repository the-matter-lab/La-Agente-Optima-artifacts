from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor

from .space import Candidate, SearchSpace


@dataclass
class SuggestionConfig:
    init_random: int = 12
    candidate_pool_size: int = 1024
    random_explore_prob: float = 0.12
    n_trees: int = 512
    min_successes_for_model: int = 8
    ei_xi: float = 0.01


class BOSuggester:
    def __init__(self, space: SearchSpace, config: SuggestionConfig, rng: random.Random) -> None:
        self.space = space
        self.config = config
        self.rng = rng

    def suggest(self, history: Sequence[dict]) -> Candidate:
        seen_keys = [
            (
                item["parameter_values"]["base"],
                item["parameter_values"]["ligand"],
                item["parameter_values"]["solvent"],
                float(item["parameter_values"]["concentration"]),
                int(item["parameter_values"]["temperature_c"]),
            )
            for item in history
        ]
        if len(history) < self.config.init_random:
            return self.space.sample_unique(self.rng, seen_keys)

        successes = [item for item in history if item["status"] == "success"]
        if len(successes) < self.config.min_successes_for_model:
            return self.space.sample_unique(self.rng, seen_keys)
        if self.rng.random() < self.config.random_explore_prob:
            return self.space.sample_unique(self.rng, seen_keys)

        try:
            return self._model_guided_suggestion(history, successes, seen_keys)
        except Exception:  # noqa: BLE001
            return self.space.sample_unique(self.rng, seen_keys)

    def _model_guided_suggestion(
        self,
        history: Sequence[dict],
        successes: Sequence[dict],
        seen_keys: Sequence[tuple],
    ) -> Candidate:
        train_candidates = [
            Candidate(**item["parameter_values"])
            for item in successes
        ]
        X = np.asarray(self.space.encode_many(train_candidates), dtype=float)
        y = np.asarray([item["objective_values"]["yield"] for item in successes], dtype=float)
        model = ExtraTreesRegressor(
            n_estimators=self.config.n_trees,
            random_state=self.rng.randint(0, 2**31 - 1),
            min_samples_leaf=1,
            bootstrap=False,
            n_jobs=1,
        )
        model.fit(X, y)

        pool = self.space.sample_pool(self.rng, seen_keys, self.config.candidate_pool_size)
        pool_X = np.asarray(self.space.encode_many(pool), dtype=float)
        tree_preds = np.stack([tree.predict(pool_X) for tree in model.estimators_], axis=0)
        mu = tree_preds.mean(axis=0)
        sigma = tree_preds.std(axis=0, ddof=0)
        incumbent = float(y.max())
        eis = np.asarray([
            _expected_improvement(m, s, incumbent, self.config.ei_xi)
            for m, s in zip(mu, sigma)
        ])
        best_idx = int(np.argmax(eis))
        return pool[best_idx]


def _normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _expected_improvement(mu: float, sigma: float, best: float, xi: float) -> float:
    improvement = mu - best - xi
    if sigma <= 1e-12:
        return max(0.0, improvement)
    z = improvement / sigma
    return improvement * _normal_cdf(z) + sigma * _normal_pdf(z)
