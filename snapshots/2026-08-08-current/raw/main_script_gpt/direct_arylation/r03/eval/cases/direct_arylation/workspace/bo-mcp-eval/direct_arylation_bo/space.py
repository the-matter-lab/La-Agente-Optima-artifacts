from __future__ import annotations

from datetime import datetime, timezone

INVOCATION_MARKER = "akg-eval-b39a08cc7a4346709f3b2b030751f55c"
CACHE_BUSTER_NONCE = "781f35d8-caf8-4056-b13b-b664a37b1fc8"
OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"
OBJECTIVE_DIRECTION = "maximize"

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

SOLVENT_VALUES = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]
CONCENTRATION_VALUES = [0.057, 0.1, 0.153]
TEMPERATURE_VALUES = [90, 105, 120]


def build_campaign_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_nonce = CACHE_BUSTER_NONCE.split("-")[0]
    return f"direct-arylation-{INVOCATION_MARKER}-{short_nonce}-{stamp}"


def build_intake(name: str, random_seed: int) -> dict:
    return {
        "name": name,
        "description": (
            "Direct arylation reaction-yield optimization over fixed fully crossed "
            f"benchmark space; invocation_marker={INVOCATION_MARKER}; "
            f"cache_buster_nonce={CACHE_BUSTER_NONCE}"
        ),
        "backend": "baybe",
        "batch_size": 1,
        "initial_design_size": 12,
        "random_seed": random_seed,
        "parameters": [
            {"name": "base", "type": "categorical", "categories": BASE_VALUES},
            {"name": "ligand", "type": "categorical", "categories": LIGAND_VALUES},
            {"name": "solvent", "type": "categorical", "categories": SOLVENT_VALUES},
            {"name": "concentration", "type": "discrete", "values": CONCENTRATION_VALUES},
            {"name": "temperature_c", "type": "discrete", "values": TEMPERATURE_VALUES},
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }
