from __future__ import annotations

from typing import Any

BASE_VALUES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGAND_VALUES = [
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

SOLVENT_VALUES = [
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATION_VALUES = [0.057, 0.1, 0.153]
TEMPERATURE_VALUES = [90, 105, 120]

PARAMETER_ORDER = [
    "base",
    "ligand",
    "solvent",
    "concentration",
    "temperature_c",
]

SEARCH_SPACE = {
    "base": BASE_VALUES,
    "ligand": LIGAND_VALUES,
    "solvent": SOLVENT_VALUES,
    "concentration": CONCENTRATION_VALUES,
    "temperature_c": TEMPERATURE_VALUES,
}


def _coerce_choice(name: str, value: Any, allowed: list[Any]) -> Any:
    if name in {"concentration", "temperature_c"}:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {name}: {value!r}") from exc
        best = min(allowed, key=lambda item: abs(float(item) - numeric))
        if abs(float(best) - numeric) > 1e-9:
            raise ValueError(f"Unexpected {name}: {value!r}")
        return int(best) if name == "temperature_c" else float(best)
    if value in allowed:
        return value
    raise ValueError(f"Unexpected {name}: {value!r}")


def normalize_parameter_values(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in PARAMETER_ORDER if name not in raw]
    if missing:
        raise ValueError(f"Missing parameter(s): {', '.join(missing)}")
    return {
        "base": _coerce_choice("base", raw["base"], BASE_VALUES),
        "ligand": _coerce_choice("ligand", raw["ligand"], LIGAND_VALUES),
        "solvent": _coerce_choice("solvent", raw["solvent"], SOLVENT_VALUES),
        "concentration": _coerce_choice("concentration", raw["concentration"], CONCENTRATION_VALUES),
        "temperature_c": _coerce_choice("temperature_c", raw["temperature_c"], TEMPERATURE_VALUES),
    }


def parameter_definitions() -> list[dict[str, Any]]:
    return [
        {"name": "base", "type": "categorical", "categories": BASE_VALUES},
        {"name": "ligand", "type": "categorical", "categories": LIGAND_VALUES},
        {"name": "solvent", "type": "categorical", "categories": SOLVENT_VALUES},
        {"name": "concentration", "type": "discrete", "values": CONCENTRATION_VALUES},
        {"name": "temperature_c", "type": "discrete", "values": TEMPERATURE_VALUES},
    ]
