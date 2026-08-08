from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Dict, Iterable, List, Sequence, Tuple


BASES: Tuple[str, ...] = (
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
)

LIGANDS: Tuple[str, ...] = (
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
)

SOLVENTS: Tuple[str, ...] = (
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
)

CONCENTRATIONS: Tuple[float, ...] = (0.057, 0.1, 0.153)
TEMPERATURES_C: Tuple[int, ...] = (90, 105, 120)


@dataclass(frozen=True)
class Candidate:
    base: str
    ligand: str
    solvent: str
    concentration: float
    temperature_c: int

    def to_parameter_values(self) -> Dict[str, object]:
        return {
            "base": self.base,
            "ligand": self.ligand,
            "solvent": self.solvent,
            "concentration": self.concentration,
            "temperature_c": self.temperature_c,
        }

    def key(self) -> Tuple[object, ...]:
        return (
            self.base,
            self.ligand,
            self.solvent,
            float(self.concentration),
            int(self.temperature_c),
        )


class SearchSpace:
    def __init__(self) -> None:
        self._bases = BASES
        self._ligands = LIGANDS
        self._solvents = SOLVENTS
        self._concentrations = CONCENTRATIONS
        self._temperatures = TEMPERATURES_C
        self._base_index = {v: i for i, v in enumerate(self._bases)}
        self._ligand_index = {v: i for i, v in enumerate(self._ligands)}
        self._solvent_index = {v: i for i, v in enumerate(self._solvents)}
        self._conc_values = list(self._concentrations)
        self._temp_values = list(self._temperatures)
        self.dim = len(self._bases) + len(self._ligands) + len(self._solvents) + 2

    @property
    def size(self) -> int:
        return (
            len(self._bases)
            * len(self._ligands)
            * len(self._solvents)
            * len(self._concentrations)
            * len(self._temperatures)
        )

    def sample_unique(self, rng: random.Random, seen: Iterable[Tuple[object, ...]]) -> Candidate:
        seen_keys = set(seen)
        if len(seen_keys) >= self.size:
            raise RuntimeError("Search space exhausted")
        while True:
            cand = Candidate(
                base=rng.choice(self._bases),
                ligand=rng.choice(self._ligands),
                solvent=rng.choice(self._solvents),
                concentration=rng.choice(self._concentrations),
                temperature_c=rng.choice(self._temperatures),
            )
            if cand.key() not in seen_keys:
                return cand

    def sample_pool(
        self,
        rng: random.Random,
        seen: Iterable[Tuple[object, ...]],
        pool_size: int,
    ) -> List[Candidate]:
        seen_keys = set(seen)
        target = min(pool_size, self.size - len(seen_keys))
        pool: List[Candidate] = []
        pool_keys = set()
        while len(pool) < target:
            cand = self.sample_unique(rng, seen_keys | pool_keys)
            pool.append(cand)
            pool_keys.add(cand.key())
        return pool

    def encode_many(self, candidates: Sequence[Candidate]) -> List[List[float]]:
        return [self.encode(c) for c in candidates]

    def encode(self, candidate: Candidate) -> List[float]:
        x = [0.0] * self.dim
        x[self._base_index[candidate.base]] = 1.0
        offset = len(self._bases)
        x[offset + self._ligand_index[candidate.ligand]] = 1.0
        offset += len(self._ligands)
        x[offset + self._solvent_index[candidate.solvent]] = 1.0
        offset += len(self._solvents)
        x[offset] = self._scale_numeric(candidate.concentration, self._conc_values)
        x[offset + 1] = self._scale_numeric(candidate.temperature_c, self._temp_values)
        return x

    @staticmethod
    def _scale_numeric(value: float, choices: Sequence[float]) -> float:
        lo = min(choices)
        hi = max(choices)
        return 0.0 if hi == lo else (float(value) - lo) / (hi - lo)
