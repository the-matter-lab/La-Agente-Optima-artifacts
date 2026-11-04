from __future__ import annotations

import json
from typing import Any

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
PARAMETER_NAMES = ["base", "ligand", "solvent", "concentration", "temperature_c"]


def build_parameters() -> list[dict[str, Any]]:
    return [
        {"name": "base", "type": "categorical", "categories": BASES},
        {"name": "ligand", "type": "categorical", "categories": LIGANDS},
        {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]


def canonicalize_parameter_values(parameter_values: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": str(parameter_values["base"]),
        "ligand": str(parameter_values["ligand"]),
        "solvent": str(parameter_values["solvent"]),
        "concentration": float(parameter_values["concentration"]),
        "temperature_c": int(parameter_values["temperature_c"]),
    }


def format_parameters(parameter_values: dict[str, Any]) -> str:
    values = canonicalize_parameter_values(parameter_values)
    return ", ".join(f"{name}={values[name]}" for name in PARAMETER_NAMES)


def parameter_fingerprint(parameter_values: dict[str, Any]) -> str:
    values = canonicalize_parameter_values(parameter_values)
    return json.dumps(values, sort_keys=True, separators=(",", ":"))
