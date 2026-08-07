from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np

PARAMETER_ORDER = ["base", "ligand", "solvent", "concentration", "temperature_c"]
SPACE = {
    "base": [
        "Potassium acetate",
        "Potassium pivalate",
        "Cesium acetate",
        "Cesium pivalate",
    ],
    "ligand": [
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
    ],
    "solvent": ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"],
    "concentration": [0.057, 0.1, 0.153],
    "temperature_c": [90, 105, 120],
}


Candidate = dict[str, Any]


def normalize_candidate(candidate: Candidate) -> Candidate:
    return {
        "base": str(candidate["base"]),
        "ligand": str(candidate["ligand"]),
        "solvent": str(candidate["solvent"]),
        "concentration": float(candidate["concentration"]),
        "temperature_c": int(candidate["temperature_c"]),
    }


def candidate_key(candidate: Candidate) -> tuple[Any, ...]:
    c = normalize_candidate(candidate)
    return tuple(c[name] for name in PARAMETER_ORDER)


def candidate_from_key(key: tuple[Any, ...]) -> Candidate:
    return {name: value for name, value in zip(PARAMETER_ORDER, key, strict=True)}


def sample_random_candidate(rng: np.random.Generator, exclude: set[tuple[Any, ...]] | None = None) -> Candidate:
    exclude = exclude or set()
    for _ in range(10000):
        candidate = {
            "base": rng.choice(SPACE["base"]).item(),
            "ligand": rng.choice(SPACE["ligand"]).item(),
            "solvent": rng.choice(SPACE["solvent"]).item(),
            "concentration": float(rng.choice(SPACE["concentration"])),
            "temperature_c": int(rng.choice(SPACE["temperature_c"])),
        }
        if candidate_key(candidate) not in exclude:
            return candidate
    raise RuntimeError("Unable to sample an unseen candidate from the finite search space.")


def sample_random_candidates(
    rng: np.random.Generator,
    n: int,
    exclude: set[tuple[Any, ...]] | None = None,
) -> list[Candidate]:
    exclude = set(exclude or set())
    sampled: list[Candidate] = []
    for _ in range(n):
        candidate = sample_random_candidate(rng=rng, exclude=exclude)
        key = candidate_key(candidate)
        sampled.append(candidate)
        exclude.add(key)
    return sampled


@dataclass
class OneHotInteractionEncoder:
    main_feature_names: list[str]
    interaction_feature_names: list[str]
    group_slices: dict[str, slice]

    @classmethod
    def build(cls) -> "OneHotInteractionEncoder":
        main_feature_names: list[str] = []
        group_slices: dict[str, slice] = {}
        start = 0
        for name in PARAMETER_ORDER:
            levels = SPACE[name]
            end = start + len(levels)
            group_slices[name] = slice(start, end)
            main_feature_names.extend([f"{name}={level}" for level in levels])
            start = end
        interaction_feature_names: list[str] = []
        for left, right in combinations(PARAMETER_ORDER, 2):
            for left_level in SPACE[left]:
                for right_level in SPACE[right]:
                    interaction_feature_names.append(f"{left}={left_level}__{right}={right_level}")
        return cls(
            main_feature_names=main_feature_names,
            interaction_feature_names=interaction_feature_names,
            group_slices=group_slices,
        )

    @property
    def n_main(self) -> int:
        return len(self.main_feature_names)

    @property
    def n_features(self) -> int:
        return len(self.main_feature_names) + len(self.interaction_feature_names)

    def encode(self, candidates: list[Candidate]) -> np.ndarray:
        x_main = np.zeros((len(candidates), self.n_main), dtype=float)
        for row_idx, candidate in enumerate(candidates):
            c = normalize_candidate(candidate)
            cursor = 0
            for name in PARAMETER_ORDER:
                levels = SPACE[name]
                level_idx = levels.index(c[name])
                x_main[row_idx, cursor + level_idx] = 1.0
                cursor += len(levels)
        features = [x_main]
        for left, right in combinations(PARAMETER_ORDER, 2):
            left_block = x_main[:, self.group_slices[left]]
            right_block = x_main[:, self.group_slices[right]]
            interaction = np.einsum("bi,bj->bij", left_block, right_block).reshape(len(candidates), -1)
            features.append(interaction)
        return np.concatenate(features, axis=1)
