"""Fixed search space + campaign intake for the direct-arylation yield campaign.

Search space is fully crossed / categorical-discrete (4 * 12 * 4 * 3 * 3 =
1728 combinations), matching the benchmark's measured-reaction table.
Parameter names/values are preserved exactly as given by the user, including
the ``Butyornitrile`` spelling.
"""
from __future__ import annotations

import zlib

MARKER = "akg-eval-115631eb4ad043529f2b64b9751e1583"
CAMPAIGN_NAME = f"direct-arylation-yield-bo-{MARKER}"

OBJECTIVE_NAME = "yield"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "%"

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
TEMPERATURE_C_VALUES = [90, 105, 120]

PARAMETERS = [
    {"name": "base", "type": "categorical", "categories": BASE_VALUES},
    {"name": "ligand", "type": "categorical", "categories": LIGAND_VALUES},
    {"name": "solvent", "type": "categorical", "categories": SOLVENT_VALUES},
    {"name": "concentration", "type": "discrete", "values": CONCENTRATION_VALUES},
    {"name": "temperature_c", "type": "discrete", "values": [float(v) for v in TEMPERATURE_C_VALUES]},
]


def _stable_seed(nonce: str) -> int:
    return zlib.crc32(nonce.encode("utf-8")) & 0xFFFF


def build_intake(*, nonce: str, initial_design_size: int = 12) -> dict:
    """Build the BO-MCP campaign intake, pinned to the BayBE backend.

    A fully categorical/discrete crossed search space (no continuous
    dimensions) is BayBE's core use case, so the backend is pinned rather
    than left on 'auto'.
    """
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Maximize measured direct-arylation reaction yield (%) over a "
            "fixed 1728-point crossed search space (base x ligand x solvent x "
            "concentration x temperature_c), oracle-evaluated via "
            f"DIRECT_ARYLATION_API_URL. cache_buster_nonce={nonce}"
        ),
        "backend": "baybe",
        "batch_size": 1,
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
        "parameters": PARAMETERS,
        "initial_design_size": initial_design_size,
        "random_seed": _stable_seed(nonce),
    }
