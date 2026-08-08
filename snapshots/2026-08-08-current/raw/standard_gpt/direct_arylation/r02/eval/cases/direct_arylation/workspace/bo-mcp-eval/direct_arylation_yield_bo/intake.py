from __future__ import annotations

from typing import Any

from .search_space import (
    CACHE_BUSTER_NONCE,
    DEFAULT_CAMPAIGN_MAX_OBSERVATIONS,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_RANDOM_SEED,
    OBJECTIVE_NAME,
    TOTAL_SEARCH_SPACE_SIZE,
    campaign_name,
    objective_definition,
    parameter_definitions,
)


def build_intake(
    *,
    max_observations: int = DEFAULT_CAMPAIGN_MAX_OBSERVATIONS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE,
) -> dict[str, Any]:
    return {
        "name": campaign_name(),
        "description": (
            "Direct arylation measured-yield optimization over the fixed fully crossed "
            f"{TOTAL_SEARCH_SPACE_SIZE}-reaction search space. "
            f"Objective={OBJECTIVE_NAME}. Cache-buster nonce={CACHE_BUSTER_NONCE}."
        ),
        "parameters": parameter_definitions(),
        "objectives": [objective_definition()],
        "batch_size": 1,
        "initial_design_size": initial_design_size,
        "max_observations": max_observations,
        "random_seed": random_seed,
        "backend": "auto",
    }
