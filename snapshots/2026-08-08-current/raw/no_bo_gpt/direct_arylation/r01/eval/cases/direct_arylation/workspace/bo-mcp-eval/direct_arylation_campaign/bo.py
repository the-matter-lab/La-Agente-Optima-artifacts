from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import OneHotEncoder

from .space import PARAMETER_ORDER

Candidate = Dict[str, object]


@dataclass
class SurrogateBundle:
    encoder: OneHotEncoder
    model: RandomForestRegressor


def _rows(candidates: Sequence[Candidate]) -> List[List[object]]:
    return [[candidate[name] for name in PARAMETER_ORDER] for candidate in candidates]


def fit_surrogate(candidates: Sequence[Candidate], objectives: Sequence[float], seed: int) -> SurrogateBundle:
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    x = encoder.fit_transform(_rows(candidates))
    y = np.asarray(objectives, dtype=float)
    model = RandomForestRegressor(
        n_estimators=400,
        min_samples_leaf=2,
        random_state=seed,
        n_jobs=1,
    )
    model.fit(x, y)
    return SurrogateBundle(encoder=encoder, model=model)


def score_candidates(bundle: SurrogateBundle, candidates: Sequence[Candidate]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = bundle.encoder.transform(_rows(candidates))
    tree_predictions = np.asarray([tree.predict(x) for tree in bundle.model.estimators_], dtype=float)
    mean = tree_predictions.mean(axis=0)
    std = tree_predictions.std(axis=0)
    optimistic = mean + 1.25 * std
    return mean, std, optimistic
