"""Search space for the direct arylation yield campaign (1,728 fully crossed conditions)."""

OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"
PARAM_NAMES = ("base", "ligand", "solvent", "concentration", "temperature_c")

BASES = ["Potassium acetate", "Potassium pivalate", "Cesium acetate", "Cesium pivalate"]
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
SOLVENTS = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]  # spelling is intentional
CONCENTRATIONS = [0.057, 0.1, 0.153]
TEMPERATURES_C = [90.0, 105.0, 120.0]


def _categorical(name: str, categories: list[str]) -> dict:
    # One-hot encoding: labels carry no usable ordinal/chemical order here.
    return {
        "name": name,
        "type": "categorical",
        "categories": categories,
        "parameter_options": {"baybe": {"encoding": "OHE"}},
    }


def parameters() -> list[dict]:
    return [
        _categorical("base", BASES),
        _categorical("ligand", LIGANDS),
        _categorical("solvent", SOLVENTS),
        {"name": "concentration", "type": "discrete", "values": CONCENTRATIONS},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURES_C},
    ]


def oracle_payload(parameter_values: dict) -> dict:
    """Snap a suggestion onto the exact grid values the oracle accepts."""

    def nearest(value: float, grid: list[float]) -> float:
        return min(grid, key=lambda g: abs(g - float(value)))

    return {
        "base": str(parameter_values["base"]),
        "ligand": str(parameter_values["ligand"]),
        "solvent": str(parameter_values["solvent"]),
        "concentration": nearest(parameter_values["concentration"], CONCENTRATIONS),
        "temperature_c": int(nearest(parameter_values["temperature_c"], TEMPERATURES_C)),
    }
