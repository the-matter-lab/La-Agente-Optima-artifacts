"""Search-space and campaign-intake construction for the direct-arylation benchmark.

Fixed, fully-crossed search space (1,728 candidates): base x ligand x solvent x
concentration x temperature_c. Values and spellings are preserved exactly as
specified by the benchmark (including "Butyornitrile").
"""

MARKER = "akg-eval-87b85822029643db89946580a5362018"
CAMPAIGN_NAME = f"direct-arylation-yield-{MARKER}"

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

OBJECTIVE_NAME = "yield"


def build_intake(*, batch_size: int, initial_design_size: int) -> dict:
    """Build the BO-MCP campaign intake payload (BayBE backend, single objective)."""
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Direct arylation reaction-yield optimization over a fixed, fully "
            "crossed 1728-candidate search space; every measurement comes from "
            "the DIRECT_ARYLATION_API_URL oracle. Marker: " + MARKER
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "parameters": [
            {"name": "base", "type": "categorical", "categories": BASES},
            {"name": "ligand", "type": "categorical", "categories": LIGANDS},
            {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
            {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
            {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
        ],
        "objectives": [
            {"name": OBJECTIVE_NAME, "direction": "maximize", "unit": "percent"},
        ],
    }
