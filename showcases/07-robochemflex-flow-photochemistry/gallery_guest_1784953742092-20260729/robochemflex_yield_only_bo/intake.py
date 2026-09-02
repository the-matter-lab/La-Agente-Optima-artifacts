from __future__ import annotations

from robochemflex_yield_bo.space import bo_parameters


def build_intake(name: str, light_values: list[int] | None = None) -> dict:
    return {
        "name": name,
        "description": "Yield-only RoboChemFlex photochemical-flow optimization seeded from valid historical RoboFlex results.",
        "backend": "baybe",
        "batch_size": 1,
        "acquisition_method": "expected_improvement",
        "parameters": bo_parameters(light_values),
        "objectives": [
            {
                "name": "yield_percent",
                "direction": "maximize",
                "unit": "%",
                "normalization_bounds": [0.0, 100.0],
            }
        ],
        "random_seed": 650,
    }
