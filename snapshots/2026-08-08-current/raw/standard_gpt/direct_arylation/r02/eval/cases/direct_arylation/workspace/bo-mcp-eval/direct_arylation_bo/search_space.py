from __future__ import annotations

MARKER = "akg-eval-e57752da9fc444fe8fad4fc363fd1b2b"
CAMPAIGN_SLUG = "direct_arylation_bo"
CAMPAIGN_NAME = f"direct-arylation-yield-{MARKER}-baybe"
ARTIFACT_ROOT = f"artifacts/{CAMPAIGN_SLUG}_{MARKER}"
OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"

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


def build_parameters() -> list[dict[str, object]]:
    return [
        {"name": "base", "type": "categorical", "categories": BASES},
        {"name": "ligand", "type": "categorical", "categories": LIGANDS},
        {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]


def search_space_size() -> int:
    return len(BASES) * len(LIGANDS) * len(SOLVENTS) * len(CONCENTRATIONS) * len(TEMPERATURES_C)
