"""Search space definition for direct arylation reaction optimization."""

from typing import Any

# Categorical parameter options (must match oracle API exactly)
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

SOLVENTS = [
    "DMAc",
    "Butyornitrile",  # Spelling must be preserved exactly
    "Butyl Ester",
    "p-Xylene",
]

# Discrete numeric values for oracle API and BO-MCP (exact types)
CONCENTRATIONS = [0.057, 0.1, 0.153]
TEMPERATURES_C = [90, 105, 120]

# Total search space size: 4 * 12 * 4 * 3 * 3 = 1,728


def get_parameter_definitions() -> list[dict[str, Any]]:
    """Return BO-MCP parameter definitions for the campaign intake.
    
    Uses 'discrete' type for concentration and temperature_c with explicit numeric values.
    """
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": BASES,
            "description": "Base reagent for the reaction",
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": LIGANDS,
            "description": "Ligand for the palladium catalyst",
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": SOLVENTS,
            "description": "Reaction solvent (note: Butyornitrile spelling is exact)",
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": CONCENTRATIONS,
            "description": "Substrate concentration in M",
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": TEMPERATURES_C,
            "description": "Reaction temperature in Celsius",
        },
    ]


def get_objective_definition() -> dict[str, Any]:
    """Return BO-MCP objective definition for yield maximization."""
    return {
        "name": "yield",
        "target_mode": "maximize",
        "unit": "percent",
    }


def validate_candidate(candidate: dict[str, Any]) -> bool:
    """Validate that a candidate has all required parameters with valid values."""
    required = {"base", "ligand", "solvent", "concentration", "temperature_c"}
    if not required.issubset(candidate.keys()):
        return False
    return (
        candidate["base"] in BASES
        and candidate["ligand"] in LIGANDS
        and candidate["solvent"] in SOLVENTS
        and candidate["concentration"] in CONCENTRATIONS
        and candidate["temperature_c"] in TEMPERATURES_C
    )


def candidate_to_oracle_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert candidate dict to oracle API payload format."""
    return {
        "base": candidate["base"],
        "ligand": candidate["ligand"],
        "solvent": candidate["solvent"],
        "concentration": candidate["concentration"],
        "temperature_c": candidate["temperature_c"],
    }