from __future__ import annotations

from .search_space import TARGET_ANGLE_DEG, build_parameters


def build_intake(*, name: str, description: str, random_seed: int) -> dict[str, object]:
    return {
        "name": name,
        "description": description,
        "backend": "baybe",
        "batch_size": 1,
        "random_seed": random_seed,
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "static_contact_angle",
                "target_mode": "match",
                "target": TARGET_ANGLE_DEG,
                "match_shape": "absolute",
                "unit": "degree",
            }
        ],
    }
