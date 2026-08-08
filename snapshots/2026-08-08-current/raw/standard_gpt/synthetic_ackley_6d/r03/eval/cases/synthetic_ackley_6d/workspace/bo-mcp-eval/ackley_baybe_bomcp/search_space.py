from __future__ import annotations

from typing import Mapping

from . import OBJECTIVE_NAME, OBJECTIVE_UNIT

DIMENSION = 6
PARAMETER_NAMES = tuple(f"x_{index}" for index in range(1, DIMENSION + 1))


def build_parameters() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": f"Normalized Ackley coordinate {name}",
        }
        for name in PARAMETER_NAMES
    ]


def build_objectives() -> list[dict[str, object]]:
    return [
        {
            "name": OBJECTIVE_NAME,
            "direction": "maximize",
            "unit": OBJECTIVE_UNIT,
        }
    ]


def canonical_parameter_key(parameter_values: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(f"{float(parameter_values[name]):.12f}" for name in PARAMETER_NAMES)


def ordered_parameter_values(parameter_values: Mapping[str, float]) -> dict[str, float]:
    return {name: float(parameter_values[name]) for name in PARAMETER_NAMES}
