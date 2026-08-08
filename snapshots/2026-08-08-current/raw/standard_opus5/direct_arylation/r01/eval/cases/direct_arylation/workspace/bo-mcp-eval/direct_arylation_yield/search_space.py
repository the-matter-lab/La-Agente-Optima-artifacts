"""Fixed, fully crossed search space of the direct arylation benchmark.

4 bases x 12 ligands x 4 solvents x 3 concentrations x 3 temperatures = 1728.
Parameter names and category spellings are exact and must not be altered
(note in particular the benchmark spelling ``Butyornitrile``).
"""

from __future__ import annotations

OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"
OBJECTIVE_DIRECTION = "maximize"

PARAMETER_NAMES: tuple[str, ...] = (
    "base",
    "ligand",
    "solvent",
    "concentration",
    "temperature_c",
)

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

TEMPERATURES_C = [90.0, 105.0, 120.0]

SIZE = len(BASES) * len(LIGANDS) * len(SOLVENTS) * len(CONCENTRATIONS) * len(TEMPERATURES_C)


def parameters() -> list[dict]:
    """BO-MCP ``InputParameter`` payloads for the fixed search space."""
    categorical = {"baybe": {"encoding": "OHE"}}
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": BASES,
            "parameter_options": categorical,
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": LIGANDS,
            "parameter_options": categorical,
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": SOLVENTS,
            "parameter_options": categorical,
        },
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]


def canonical_parameter_values(raw: dict) -> dict:
    """Project a suggestion onto the exact five lowercase benchmark keys."""
    values = {name: raw[name] for name in PARAMETER_NAMES}
    values["concentration"] = float(values["concentration"])
    values["temperature_c"] = float(values["temperature_c"])
    return values
