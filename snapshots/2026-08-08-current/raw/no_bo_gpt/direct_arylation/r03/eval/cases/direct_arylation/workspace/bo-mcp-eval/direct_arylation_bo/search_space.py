from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence
import random

BASES: Sequence[str] = (
    'Potassium acetate',
    'Potassium pivalate',
    'Cesium acetate',
    'Cesium pivalate',
)

LIGANDS: Sequence[str] = (
    'BrettPhos',
    'Di-tert-butylphenylphosphine',
    '(t-Bu)PhCPhos',
    'Tricyclohexylphosphine',
    'PPh3',
    'XPhos',
    'P(2-furyl)3',
    'Methyldiphenylphosphine',
    '1268824-69-6',
    'JackiePhos',
    'SCHEMBL15068049',
    'Me2PPh',
)

SOLVENTS: Sequence[str] = (
    'DMAc',
    'Butyornitrile',
    'Butyl Ester',
    'p-Xylene',
)

CONCENTRATIONS: Sequence[float] = (0.057, 0.1, 0.153)
TEMPERATURES_C: Sequence[int] = (90, 105, 120)

PARAMETER_ORDER = ('base', 'ligand', 'solvent', 'concentration', 'temperature_c')
CATEGORICAL_ORDER = ('base', 'ligand', 'solvent')
NUMERIC_ORDER = ('concentration', 'temperature_c')

CATEGORY_VALUES = {
    'base': tuple(BASES),
    'ligand': tuple(LIGANDS),
    'solvent': tuple(SOLVENTS),
}
NUMERIC_VALUES = {
    'concentration': tuple(CONCENTRATIONS),
    'temperature_c': tuple(TEMPERATURES_C),
}


@dataclass(frozen=True)
class Candidate:
    base: str
    ligand: str
    solvent: str
    concentration: float
    temperature_c: int

    def to_parameter_values(self) -> Dict[str, object]:
        return {
            'base': self.base,
            'ligand': self.ligand,
            'solvent': self.solvent,
            'concentration': float(self.concentration),
            'temperature_c': int(self.temperature_c),
        }

    def key(self) -> tuple:
        return (
            self.base,
            self.ligand,
            self.solvent,
            round(float(self.concentration), 3),
            int(self.temperature_c),
        )


def random_candidate(rng: random.Random) -> Candidate:
    return Candidate(
        base=rng.choice(list(BASES)),
        ligand=rng.choice(list(LIGANDS)),
        solvent=rng.choice(list(SOLVENTS)),
        concentration=float(rng.choice(list(CONCENTRATIONS))),
        temperature_c=int(rng.choice(list(TEMPERATURES_C))),
    )


def sample_unique_candidates(rng: random.Random, n: int, seen_keys: set[tuple]) -> List[Candidate]:
    picks: List[Candidate] = []
    local_seen = set(seen_keys)
    max_size = len(BASES) * len(LIGANDS) * len(SOLVENTS) * len(CONCENTRATIONS) * len(TEMPERATURES_C)
    target = min(n, max_size - len(local_seen))
    while len(picks) < target:
        cand = random_candidate(rng)
        key = cand.key()
        if key in local_seen:
            continue
        local_seen.add(key)
        picks.append(cand)
    return picks


def encode_candidates(candidates: Sequence[Candidate]) -> List[List[float]]:
    rows: List[List[float]] = []
    conc_values = list(CONCENTRATIONS)
    temp_values = list(TEMPERATURES_C)
    conc_min, conc_max = min(conc_values), max(conc_values)
    temp_min, temp_max = min(temp_values), max(temp_values)
    for cand in candidates:
        row: List[float] = []
        for name in CATEGORICAL_ORDER:
            values = CATEGORY_VALUES[name]
            selected = getattr(cand, name)
            row.extend(1.0 if v == selected else 0.0 for v in values)
        row.append((float(cand.concentration) - conc_min) / (conc_max - conc_min))
        row.append((float(cand.temperature_c) - temp_min) / (temp_max - temp_min))
        rows.append(row)
    return rows
