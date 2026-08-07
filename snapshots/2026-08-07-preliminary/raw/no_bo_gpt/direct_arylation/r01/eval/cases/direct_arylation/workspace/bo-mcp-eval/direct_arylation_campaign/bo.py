from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Any

import numpy as np


BASES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]
LIGANDS = [
    "BrettPhos",
    "Di-tert-butylphenylphosphine",
    "(t-Bu)PhCPhos",
    "Tricyclohexylphosphine",
    "PPh3",
    "XPhos",
    "P(2-furyl)3",
    "Methyldiphenylphosphine",
    "1268824-69-6",
    "JackiePhos",
    "SCHEMBL15068049",
    "Me2PPh",
]
SOLVENTS = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]
CONCENTRATIONS = [0.057, 0.1, 0.153]
TEMPERATURES_C = [90, 105, 120]


@dataclass(frozen=True)
class Candidate:
    base: str
    ligand: str
    solvent: str
    concentration: float
    temperature_c: int

    def to_parameter_values(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "ligand": self.ligand,
            "solvent": self.solvent,
            "concentration": float(self.concentration),
            "temperature_c": int(self.temperature_c),
        }

    def key(self) -> tuple[Any, ...]:
        return (
            self.base,
            self.ligand,
            self.solvent,
            float(self.concentration),
            int(self.temperature_c),
        )


def full_search_space() -> list[Candidate]:
    return [
        Candidate(base, ligand, solvent, concentration, temperature_c)
        for base, ligand, solvent, concentration, temperature_c in product(
            BASES, LIGANDS, SOLVENTS, CONCENTRATIONS, TEMPERATURES_C
        )
    ]


class CandidateEncoder:
    def __init__(self) -> None:
        self.base_index = {v: i for i, v in enumerate(BASES)}
        self.ligand_index = {v: i for i, v in enumerate(LIGANDS)}
        self.solvent_index = {v: i for i, v in enumerate(SOLVENTS)}
        self.conc_levels = {v: i for i, v in enumerate(CONCENTRATIONS)}
        self.temp_levels = {v: i for i, v in enumerate(TEMPERATURES_C)}
        self.conc_mean = float(np.mean(CONCENTRATIONS))
        self.conc_std = float(np.std(CONCENTRATIONS))
        self.temp_mean = float(np.mean(TEMPERATURES_C))
        self.temp_std = float(np.std(TEMPERATURES_C))
        self.n_features = (
            1
            + len(BASES)
            + len(LIGANDS)
            + len(SOLVENTS)
            + len(CONCENTRATIONS)
            + len(TEMPERATURES_C)
            + 5
        )

    def encode(self, candidate: Candidate) -> np.ndarray:
        x = np.zeros(self.n_features, dtype=float)
        cursor = 0
        x[cursor] = 1.0
        cursor += 1
        x[cursor + self.base_index[candidate.base]] = 1.0
        cursor += len(BASES)
        x[cursor + self.ligand_index[candidate.ligand]] = 1.0
        cursor += len(LIGANDS)
        x[cursor + self.solvent_index[candidate.solvent]] = 1.0
        cursor += len(SOLVENTS)
        x[cursor + self.conc_levels[float(candidate.concentration)]] = 1.0
        cursor += len(CONCENTRATIONS)
        x[cursor + self.temp_levels[int(candidate.temperature_c)]] = 1.0
        cursor += len(TEMPERATURES_C)
        conc_scaled = (float(candidate.concentration) - self.conc_mean) / max(self.conc_std, 1e-8)
        temp_scaled = (int(candidate.temperature_c) - self.temp_mean) / max(self.temp_std, 1e-8)
        x[cursor : cursor + 5] = [
            conc_scaled,
            temp_scaled,
            conc_scaled * temp_scaled,
            conc_scaled**2,
            temp_scaled**2,
        ]
        return x


@dataclass
class SurrogateState:
    posterior_mean: np.ndarray
    posterior_cov: np.ndarray
    beta: float
    y_mean: float
    y_std: float


class BayesianLinearSurrogate:
    def __init__(self, encoder: CandidateEncoder, alpha: float = 1.0, noise_sigma: float = 10.0) -> None:
        self.encoder = encoder
        self.alpha = alpha
        self.noise_sigma = noise_sigma

    def fit(self, candidates: list[Candidate], yields: list[float]) -> SurrogateState:
        X = np.vstack([self.encoder.encode(c) for c in candidates])
        y = np.asarray(yields, dtype=float)
        y_mean = float(np.mean(y))
        y_std = float(np.std(y))
        y_scaled = (y - y_mean) / max(y_std, 1.0)
        beta = 1.0 / (self.noise_sigma**2)
        precision = self.alpha * np.eye(X.shape[1]) + beta * (X.T @ X)
        cov = np.linalg.inv(precision)
        mean = beta * cov @ X.T @ y_scaled
        return SurrogateState(mean, cov, beta, y_mean, max(y_std, 1.0))

    def predict(self, state: SurrogateState, candidates: list[Candidate]) -> tuple[np.ndarray, np.ndarray]:
        X = np.vstack([self.encoder.encode(c) for c in candidates])
        mean_scaled = X @ state.posterior_mean
        var_scaled = (1.0 / state.beta) + np.sum((X @ state.posterior_cov) * X, axis=1)
        mean = state.y_mean + state.y_std * mean_scaled
        std = state.y_std * np.sqrt(np.maximum(var_scaled, 1e-12))
        return mean, std


def choose_next_candidate(
    rng: np.random.Generator,
    encoder: CandidateEncoder,
    observed_candidates: list[Candidate],
    observed_yields: list[float],
    remaining_candidates: list[Candidate],
    iteration_index: int,
) -> Candidate:
    if not remaining_candidates:
        raise ValueError("No remaining candidates.")
    if len(observed_yields) < 6:
        return remaining_candidates[int(rng.integers(len(remaining_candidates)))]

    surrogate = BayesianLinearSurrogate(encoder=encoder)
    state = surrogate.fit(observed_candidates, observed_yields)
    means, stds = surrogate.predict(state, remaining_candidates)

    exploration_rate = 0.15 if len(observed_yields) < 20 else 0.08
    if rng.random() < exploration_rate:
        scores = stds
    else:
        kappa = max(0.8, 2.2 - 0.03 * iteration_index)
        scores = means + kappa * stds

    best_score = float(np.max(scores))
    near_best = [i for i, s in enumerate(scores) if math.isclose(float(s), best_score, rel_tol=1e-12, abs_tol=1e-12)]
    selected_idx = int(rng.choice(near_best)) if near_best else int(np.argmax(scores))
    return remaining_candidates[selected_idx]
