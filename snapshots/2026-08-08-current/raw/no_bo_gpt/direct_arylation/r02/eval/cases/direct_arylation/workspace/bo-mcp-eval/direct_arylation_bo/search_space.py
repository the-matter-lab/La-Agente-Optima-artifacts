from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

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

BASE_INDEX = {v: i for i, v in enumerate(BASES)}
LIGAND_INDEX = {v: i for i, v in enumerate(LIGANDS)}
SOLVENT_INDEX = {v: i for i, v in enumerate(SOLVENTS)}
CONCENTRATION_INDEX = {v: i for i, v in enumerate(CONCENTRATIONS)}
TEMPERATURE_INDEX = {v: i for i, v in enumerate(TEMPERATURES_C)}

FEATURE_DIM = len(BASES) + len(LIGANDS) + len(SOLVENTS) + 2


@dataclass(frozen=True)
class SearchSpace:
    def all_candidates(self) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for base in BASES:
            for ligand in LIGANDS:
                for solvent in SOLVENTS:
                    for concentration in CONCENTRATIONS:
                        for temperature_c in TEMPERATURES_C:
                            out.append(
                                {
                                    "base": base,
                                    "ligand": ligand,
                                    "solvent": solvent,
                                    "concentration": concentration,
                                    "temperature_c": temperature_c,
                                }
                            )
        return out

    def encode(self, candidate: Dict[str, object]) -> List[float]:
        x = [0.0] * FEATURE_DIM
        x[BASE_INDEX[str(candidate["base"])]] = 1.0
        offset = len(BASES)
        x[offset + LIGAND_INDEX[str(candidate["ligand"])]] = 1.0
        offset += len(LIGANDS)
        x[offset + SOLVENT_INDEX[str(candidate["solvent"])]] = 1.0
        offset += len(SOLVENTS)
        concentration = float(candidate["concentration"])
        temperature_c = float(candidate["temperature_c"])
        x[offset] = (concentration - min(CONCENTRATIONS)) / (max(CONCENTRATIONS) - min(CONCENTRATIONS))
        x[offset + 1] = (temperature_c - min(TEMPERATURES_C)) / (max(TEMPERATURES_C) - min(TEMPERATURES_C))
        return x

    def key(self, candidate: Dict[str, object]) -> Tuple[object, ...]:
        return (
            candidate["base"],
            candidate["ligand"],
            candidate["solvent"],
            float(candidate["concentration"]),
            int(candidate["temperature_c"]),
        )

    def to_parameter_values(self, candidate: Dict[str, object]) -> Dict[str, object]:
        return {
            "base": str(candidate["base"]),
            "ligand": str(candidate["ligand"]),
            "solvent": str(candidate["solvent"]),
            "concentration": float(candidate["concentration"]),
            "temperature_c": int(candidate["temperature_c"]),
        }


def unique_keys(candidates: Iterable[Dict[str, object]]) -> List[Tuple[object, ...]]:
    space = SearchSpace()
    return [space.key(c) for c in candidates]
