from __future__ import annotations

from .space import bo_parameters


def build_intake(name: str, light_values: list[int] | None = None) -> dict:
    return {
        "name": name,
        "description": "RoboChemFlex photochemical-flow yield optimization from workspace CSV search space.",
        "backend": "baybe",
        "batch_size": 1,
        "acquisition_method": "expected_improvement",
        "scalarization": "desirability",
        "scalarizer": "geom_mean",
        "parameters": bo_parameters(light_values),
        "objectives": [
            {
                "name": "yield_percent",
                "direction": "maximize",
                "unit": "%",
                "weight": 0.8,
                "normalization_bounds": [0.0, 100.0],
            },
            {
                "name": "green_score",
                "direction": "maximize",
                "unit": "0-100 score",
                "weight": 0.2,
                "normalization_bounds": [0.0, 100.0],
            },
        ],
        "random_seed": 650,
    }
