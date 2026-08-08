"""Search space definitions for direct arylation BO campaign."""

from typing import Any


BASE_CATEGORIES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGAND_CATEGORIES = [
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

SOLVENT_CATEGORIES = [
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATION_VALUES = [0.057, 0.1, 0.153]
TEMPERATURE_VALUES = [90, 105, 120]


def get_parameter_definitions() -> list[dict[str, Any]]:
    """Return the BO-MCP intake parameter definitions for the direct arylation search space."""
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": BASE_CATEGORIES,
            "description": "Base reagent for the reaction",
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": LIGAND_CATEGORIES,
            "description": "Ligand for the palladium catalyst",
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": SOLVENT_CATEGORIES,
            "description": "Reaction solvent",
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": CONCENTRATION_VALUES,
            "description": "Reactant concentration (M)",
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": TEMPERATURE_VALUES,
            "description": "Reaction temperature in Celsius",
        },
    ]


def get_objective_definition() -> dict[str, Any]:
    """Return the BO-MCP intake objective definition."""
    return {
        "name": "yield",
        "direction": "maximize",
        "unit": "percent",
    }


def get_search_space_size() -> int:
    """Calculate total combinatorial search space size."""
    return (
        len(BASE_CATEGORIES)
        * len(LIGAND_CATEGORIES)
        * len(SOLVENT_CATEGORIES)
        * len(CONCENTRATION_VALUES)
        * len(TEMPERATURE_VALUES)
    )