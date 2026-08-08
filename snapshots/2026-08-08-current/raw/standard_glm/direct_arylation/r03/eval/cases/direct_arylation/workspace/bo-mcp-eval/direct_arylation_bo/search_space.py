"""Search-space parameter definitions for the direct arylation campaign."""

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
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATIONS = [0.057, 0.1, 0.153]

TEMPERATURES = [90, 105, 120]

# Parameter names (lowercase, as used in the oracle API)
PARAM_NAMES = ["base", "ligand", "solvent", "concentration", "temperature_c"]


def build_parameters() -> list[dict]:
    """Return the BO-MCP intake parameter list."""
    return [
        {
            "name": "base",
            "type": "categorical",
            "categories": BASES,
        },
        {
            "name": "ligand",
            "type": "categorical",
            "categories": LIGANDS,
        },
        {
            "name": "solvent",
            "type": "categorical",
            "categories": SOLVENTS,
        },
        {
            "name": "concentration",
            "type": "discrete",
            "values": CONCENTRATIONS,
        },
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": TEMPERATURES,
        },
    ]
