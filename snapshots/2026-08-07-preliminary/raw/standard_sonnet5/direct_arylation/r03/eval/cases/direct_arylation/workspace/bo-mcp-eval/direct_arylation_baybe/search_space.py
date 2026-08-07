"""Fixed, fully-crossed search space for the direct-arylation-yield benchmark.

1,728 candidates = 4 bases x 12 ligands x 4 solvents x 3 concentrations x
3 temperatures. Names/spellings are preserved exactly as specified,
including the intentional "Butyornitrile" spelling.
"""

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


def build_parameters() -> list[dict]:
    """Return the BO-MCP `InputParameter` list for this search space."""
    return [
        {"name": "base", "type": "categorical", "categories": BASES},
        {"name": "ligand", "type": "categorical", "categories": LIGANDS},
        {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]
