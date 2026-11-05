from __future__ import annotations

from typing import Dict, List, Sequence, Tuple
import random

BASES: List[str] = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGANDS: List[str] = [
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

SOLVENTS: List[str] = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]
CONCENTRATIONS: List[float] = [0.057, 0.1, 0.153]
TEMPERATURES_C: List[int] = [90, 105, 120]

PARAMETER_ORDER: Tuple[str, ...] = (
    "base",
    "ligand",
    "solvent",
    "concentration",
    "temperature_c",
)

SPACE = {
    "base": BASES,
    "ligand": LIGANDS,
    "solvent": SOLVENTS,
    "concentration": CONCENTRATIONS,
    "temperature_c": TEMPERATURES_C,
}

Candidate = Dict[str, object]


def canonical_key(candidate: Candidate) -> Tuple[object, ...]:
    return tuple(candidate[name] for name in PARAMETER_ORDER)


def random_candidate(rng: random.Random) -> Candidate:
    return {
        "base": rng.choice(BASES),
        "ligand": rng.choice(LIGANDS),
        "solvent": rng.choice(SOLVENTS),
        "concentration": rng.choice(CONCENTRATIONS),
        "temperature_c": rng.choice(TEMPERATURES_C),
    }


def stratified_initial_design(rng: random.Random, n: int) -> List[Candidate]:
    if n <= 0:
        return []
    designs: List[Candidate] = []
    ligand_cycle = LIGANDS.copy()
    rng.shuffle(ligand_cycle)
    base_cycle = BASES.copy()
    solvent_cycle = SOLVENTS.copy()
    conc_cycle = CONCENTRATIONS.copy()
    temp_cycle = TEMPERATURES_C.copy()
    rng.shuffle(base_cycle)
    rng.shuffle(solvent_cycle)
    rng.shuffle(conc_cycle)
    rng.shuffle(temp_cycle)
    seen = set()
    i = 0
    while len(designs) < n:
        if i > 0 and i % len(ligand_cycle) == 0:
            rng.shuffle(base_cycle)
            rng.shuffle(solvent_cycle)
            rng.shuffle(conc_cycle)
            rng.shuffle(temp_cycle)
        candidate = {
            "base": base_cycle[i % len(base_cycle)],
            "ligand": ligand_cycle[i % len(ligand_cycle)],
            "solvent": solvent_cycle[(i + i // len(base_cycle)) % len(solvent_cycle)],
            "concentration": conc_cycle[(2 * i) % len(conc_cycle)],
            "temperature_c": temp_cycle[(3 * i + 1) % len(temp_cycle)],
        }
        key = canonical_key(candidate)
        if key not in seen:
            seen.add(key)
            designs.append(candidate)
        i += 1
    return designs


def mutate_candidate(rng: random.Random, candidate: Candidate, max_changes: int = 2) -> Candidate:
    proposal = dict(candidate)
    n_changes = rng.randint(1, max_changes)
    params = list(PARAMETER_ORDER)
    rng.shuffle(params)
    for name in params[:n_changes]:
        values: Sequence[object] = SPACE[name]
        current = proposal[name]
        alternatives = [value for value in values if value != current]
        proposal[name] = rng.choice(alternatives)
    return proposal


def build_candidate_pool(
    rng: random.Random,
    tried_keys: set[Tuple[object, ...]],
    top_candidates: List[Candidate],
    pool_size: int,
) -> List[Candidate]:
    pool: List[Candidate] = []
    pool_keys: set[Tuple[object, ...]] = set()

    def maybe_add(candidate: Candidate) -> None:
        key = canonical_key(candidate)
        if key in tried_keys or key in pool_keys:
            return
        pool.append(candidate)
        pool_keys.add(key)

    for candidate in top_candidates[: min(8, len(top_candidates))]:
        for _ in range(10):
            maybe_add(mutate_candidate(rng, candidate, max_changes=2))
            if len(pool) >= pool_size:
                return pool

    while len(pool) < pool_size:
        maybe_add(random_candidate(rng))
    return pool
