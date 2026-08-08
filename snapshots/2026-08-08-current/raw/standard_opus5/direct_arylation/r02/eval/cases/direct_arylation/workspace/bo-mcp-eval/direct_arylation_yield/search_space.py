"""Fixed, fully crossed search space for the direct-arylation yield benchmark."""

OBJECTIVE_NAME = "yield"

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
TEMPERATURES = [90, 105, 120]

SIZE = len(BASES) * len(LIGANDS) * len(SOLVENTS) * len(CONCENTRATIONS) * len(TEMPERATURES)


def parameters() -> list[dict]:
    return [
        {"name": "base", "type": "categorical", "categories": list(BASES)},
        {"name": "ligand", "type": "categorical", "categories": list(LIGANDS)},
        {"name": "solvent", "type": "categorical", "categories": list(SOLVENTS)},
        {"name": "concentration", "type": "discrete", "values": list(CONCENTRATIONS)},
        {
            "name": "temperature_c",
            "type": "discrete",
            "values": [float(t) for t in TEMPERATURES],
        },
    ]


def objectives() -> list[dict]:
    return [{"name": OBJECTIVE_NAME, "direction": "maximize", "unit": "percent"}]


def canonicalize(candidate: dict) -> dict:
    """Snap a suggested point onto the exact benchmark grid values."""
    concentration = min(CONCENTRATIONS, key=lambda v: abs(v - float(candidate["concentration"])))
    temperature = min(TEMPERATURES, key=lambda v: abs(v - float(candidate["temperature_c"])))
    return {
        "base": str(candidate["base"]),
        "ligand": str(candidate["ligand"]),
        "solvent": str(candidate["solvent"]),
        "concentration": concentration,
        "temperature_c": temperature,
    }
