from __future__ import annotations

from typing import Iterable

PARAMETER_NAMES = tuple(f"x_{index}" for index in range(1, 7))


def build_parameters() -> list[dict]:
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "Normalized Ackley 6D coordinate.",
        }
        for name in PARAMETER_NAMES
    ]


def canonical_point(parameter_values: dict[str, float]) -> tuple[str, ...]:
    return tuple(f"{float(parameter_values[name]):.12f}" for name in PARAMETER_NAMES)


def flatten_parameter_values(parameter_values: dict[str, float]) -> dict[str, float]:
    return {name: float(parameter_values[name]) for name in PARAMETER_NAMES}


def iter_parameter_values(parameter_values: dict[str, float]) -> Iterable[float]:
    for name in PARAMETER_NAMES:
        yield float(parameter_values[name])
