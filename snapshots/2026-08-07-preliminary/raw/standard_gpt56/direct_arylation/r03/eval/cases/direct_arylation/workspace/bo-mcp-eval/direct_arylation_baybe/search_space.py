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


def parameters() -> list[dict]:
    return [
        {"name": "base", "type": "categorical", "categories": BASES},
        {"name": "ligand", "type": "categorical", "categories": LIGANDS},
        {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]


def normalize_candidate(raw: dict) -> dict:
    candidate = {
        "base": raw["base"],
        "ligand": raw["ligand"],
        "solvent": raw["solvent"],
        "concentration": float(raw["concentration"]),
        "temperature_c": int(raw["temperature_c"]),
    }
    allowed = (BASES, LIGANDS, SOLVENTS, CONCENTRATIONS, TEMPERATURES_C)
    for value, choices in zip(candidate.values(), allowed, strict=True):
        if value not in choices:
            raise ValueError(f"BO-MCP suggested an out-of-space value: {value!r}")
    return candidate
