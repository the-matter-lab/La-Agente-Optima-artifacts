from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel


@dataclass
class SuggestionConfig:
    candidate_pool_size: int = 4096
    gp_restarts: int = 3


def unique_key(x: Sequence[float], decimals: int = 12) -> tuple[float, ...]:
    return tuple(np.round(np.asarray(x, dtype=float), decimals=decimals))


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    points = np.empty((n, d), dtype=float)
    for j in range(d):
        perm = rng.permutation(n)
        points[:, j] = (perm + rng.random(n)) / n
    return points


def fit_gp(X: np.ndarray, y: np.ndarray, config: SuggestionConfig) -> GaussianProcessRegressor:
    d = X.shape[1]
    kernel = (
        ConstantKernel(1.0, (0.1, 10.0))
        * Matern(length_scale=np.full(d, 0.2), length_scale_bounds=(1e-2, 5.0), nu=2.5)
        + WhiteKernel(noise_level=1e-8, noise_level_bounds=(1e-12, 1e-3))
    )
    gp = GaussianProcessRegressor(
        kernel=kernel,
        alpha=1e-10,
        normalize_y=True,
        n_restarts_optimizer=config.gp_restarts,
        random_state=0,
    )
    gp.fit(X, y)
    return gp


def expected_improvement(
    gp: GaussianProcessRegressor,
    Xcand: np.ndarray,
    y_best: float,
    xi: float = 0.01,
) -> np.ndarray:
    mu, sigma = gp.predict(Xcand, return_std=True)
    sigma = np.maximum(sigma, 1e-12)
    improvement = mu - y_best - xi
    z = improvement / sigma
    ei = improvement * norm.cdf(z) + sigma * norm.pdf(z)
    ei[sigma <= 1e-12] = 0.0
    return ei


def sample_candidate_pool(
    rng: np.random.Generator,
    d: int,
    size: int,
    X_seen: np.ndarray,
    y_seen: np.ndarray,
) -> np.ndarray:
    random_part = rng.random((size // 2, d))
    elite_idx = int(np.argmax(y_seen))
    elite = X_seen[elite_idx]
    local = elite + rng.normal(0.0, 0.08, size=(size - len(random_part), d))
    local = np.clip(local, 0.0, 1.0)
    return np.vstack([random_part, local])


def suggest_batch(
    X: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    rng: np.random.Generator,
    seen_keys: Iterable[tuple[float, ...]],
    config: SuggestionConfig | None = None,
) -> List[np.ndarray]:
    config = config or SuggestionConfig()
    d = X.shape[1]
    gp_X = np.array(X, copy=True)
    gp_y = np.array(y, copy=True)
    blocked = set(seen_keys)
    suggestions: List[np.ndarray] = []

    for _ in range(batch_size):
        gp = fit_gp(gp_X, gp_y, config)
        pool = sample_candidate_pool(rng, d, config.candidate_pool_size, gp_X, gp_y)
        keys = [unique_key(row) for row in pool]
        keep_mask = np.array([key not in blocked for key in keys], dtype=bool)
        filtered = pool[keep_mask]
        if filtered.size == 0:
            while True:
                proposal = rng.random(d)
                key = unique_key(proposal)
                if key not in blocked:
                    suggestions.append(proposal)
                    blocked.add(key)
                    gp_X = np.vstack([gp_X, proposal])
                    gp_y = np.append(gp_y, float(np.max(gp_y)))
                    break
            continue

        ei = expected_improvement(gp, filtered, y_best=float(np.max(gp_y)))
        order = np.argsort(ei)[::-1]
        chosen = None
        for idx in order:
            proposal = filtered[idx]
            key = unique_key(proposal)
            if key not in blocked:
                chosen = proposal
                blocked.add(key)
                break
        if chosen is None:
            while True:
                proposal = rng.random(d)
                key = unique_key(proposal)
                if key not in blocked:
                    chosen = proposal
                    blocked.add(key)
                    break
        suggestions.append(chosen)
        gp_X = np.vstack([gp_X, chosen])
        gp_y = np.append(gp_y, float(np.max(gp_y)))
    return suggestions
