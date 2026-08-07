"""Search space definition for the direct arylation benchmark."""

from typing import Any

# Categorical parameters with exact values from the benchmark
BASE_OPTIONS = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGAND_OPTIONS = [
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

SOLVENT_OPTIONS = [
    "DMAc",
    "Butyornitrile",  # Intentional spelling from benchmark
    "Butyl Ester",
    "p-Xylene",
]

# Discrete numeric parameters
CONCENTRATION_OPTIONS = [0.057, 0.1, 0.153]
TEMPERATURE_OPTIONS = [90, 105, 120]

# Total combinations: 4 * 12 * 4 * 3 * 3 = 1728

PARAMETER_NAMES = ["base", "ligand", "solvent", "concentration", "temperature_c"]


def get_search_space_parameters() -> list[dict[str, Any]]:
    """Return parameter definitions compatible with BO-MCP intake format."""
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": BASE_OPTIONS,
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": LIGAND_OPTIONS,
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": SOLVENT_OPTIONS,
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": CONCENTRATION_OPTIONS,
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": TEMPERATURE_OPTIONS,
        },
    ]


def get_parameter_options() -> dict[str, dict[str, list[Any]]]:
    """Return the valid options for each categorical/discrete parameter."""
    return {
        "base": BASE_OPTIONS,
        "ligand": LIGAND_OPTIONS,
        "solvent": SOLVENT_OPTIONS,
        "concentration": CONCENTRATION_OPTIONS,
        "temperature_c": TEMPERATURE_OPTIONS,
    }


def validate_candidate(candidate: dict[str, Any]) -> bool:
    """Validate that a candidate uses only allowed values."""
    options = get_parameter_options()
    for param, value in candidate.items():
        if param in options and value not in options[param]:
            return False
    return True