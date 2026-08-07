from __future__ import annotations

import json
from typing import Any

CACHE_BUSTER_NONCE = "f8cfd946-3972-4d92-97e3-98d984cbbd2a"
OWNERSHIP_MARKER = "akg-eval-101d38bff75e48f397a2480db7da4fb3"
CAMPAIGN_SLUG = "direct_arylation_yield_bo"
OBJECTIVE_NAME = "yield"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "percent"
TOTAL_SEARCH_SPACE_SIZE = 1728
DEFAULT_MAX_ATTEMPTS = 60
DEFAULT_CAMPAIGN_MAX_OBSERVATIONS = 60
DEFAULT_RANDOM_SEED = 20260730
DEFAULT_INITIAL_DESIGN_SIZE = 12

BASE_VALUES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGAND_VALUES = [
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

SOLVENT_VALUES = [
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATION_VALUES = [0.057, 0.1, 0.153]
TEMPERATURE_VALUES = [90, 105, 120]

assert (
    len(BASE_VALUES)
    * len(LIGAND_VALUES)
    * len(SOLVENT_VALUES)
    * len(CONCENTRATION_VALUES)
    * len(TEMPERATURE_VALUES)
    == TOTAL_SEARCH_SPACE_SIZE
)


def campaign_name() -> str:
    return f"{CAMPAIGN_SLUG}-{OWNERSHIP_MARKER}-{CACHE_BUSTER_NONCE}"


def parameter_definitions() -> list[dict[str, Any]]:
    return [
        {"name": "base", "type": "categorical", "categories": BASE_VALUES},
        {"name": "ligand", "type": "categorical", "categories": LIGAND_VALUES},
        {"name": "solvent", "type": "categorical", "categories": SOLVENT_VALUES},
        {
            "name": "concentration",
            "type": "discrete",
            "values": CONCENTRATION_VALUES,
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": TEMPERATURE_VALUES,
        },
    ]


def objective_definition() -> dict[str, Any]:
    return {
        "name": OBJECTIVE_NAME,
        "direction": OBJECTIVE_DIRECTION,
        "unit": OBJECTIVE_UNIT,
    }


def _canonical_member(value: Any, allowed: list[Any], *, numeric: bool = False) -> Any:
    if numeric:
        numeric_value = float(value)
        for allowed_value in allowed:
            if abs(numeric_value - float(allowed_value)) <= 1e-9:
                return allowed_value
        raise ValueError(f"Unexpected numeric value {value!r}; allowed values are {allowed}.")
    if value in allowed:
        return value
    raise ValueError(f"Unexpected categorical value {value!r}; allowed values are {allowed}.")


def canonical_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    canonical = {
        "base": _canonical_member(candidate["base"], BASE_VALUES),
        "ligand": _canonical_member(candidate["ligand"], LIGAND_VALUES),
        "solvent": _canonical_member(candidate["solvent"], SOLVENT_VALUES),
        "concentration": float(_canonical_member(candidate["concentration"], CONCENTRATION_VALUES, numeric=True)),
        "temperature_c": int(round(float(_canonical_member(candidate["temperature_c"], TEMPERATURE_VALUES, numeric=True)))),
    }
    return canonical


def candidate_signature(candidate: dict[str, Any]) -> str:
    return json.dumps(canonical_candidate(candidate), sort_keys=True, separators=(",", ":"))
