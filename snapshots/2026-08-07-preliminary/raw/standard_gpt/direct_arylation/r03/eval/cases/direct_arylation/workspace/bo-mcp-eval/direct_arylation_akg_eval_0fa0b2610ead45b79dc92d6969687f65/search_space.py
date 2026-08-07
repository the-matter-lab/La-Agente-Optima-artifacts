from __future__ import annotations

from pathlib import Path

MARKER = "akg-eval-0fa0b2610ead45b79dc92d6969687f65"
NONCE = "f95202f9-666a-4e6a-abd4-8c58fa52394b"
CHAT_TRACE_ID = "direct-arylation-akg-eval-0fa0b2610ead45b79dc92d6969687f65-f95202f9"
CAMPAIGN_SLUG = "direct_arylation_akg_eval_0fa0b2610ead45b79dc92d6969687f65"
CAMPAIGN_NAME = f"direct-arylation-{MARKER}"
OBJECTIVE_NAME = "yield"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "percent"
TOTAL_ATTEMPT_BUDGET = 60
DEFAULT_ARTIFACT_DIR = Path("artifacts") / CAMPAIGN_SLUG
PARAMETER_ORDER = [
    "base",
    "ligand",
    "solvent",
    "concentration",
    "temperature_c",
]

SEARCH_PARAMETERS = [
    {
        "name": "base",
        "type": "categorical",
        "categories": [
            "Potassium acetate",
            "Potassium pivalate",
            "Cesium acetate",
            "Cesium pivalate",
        ],
    },
    {
        "name": "ligand",
        "type": "categorical",
        "categories": [
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
    },
    {
        "name": "solvent",
        "type": "categorical",
        "categories": [
            "DMAc",
            "Butyornitrile",
            "Butyl Ester",
            "p-Xylene",
        ],
    },
    {
        "name": "concentration",
        "type": "discrete",
        "values": [0.057, 0.1, 0.153],
    },
    {
        "name": "temperature_c",
        "type": "discrete",
        "values": [90, 105, 120],
    },
]


def ordered_parameter_values(values: dict) -> dict:
    return {name: values[name] for name in PARAMETER_ORDER}
