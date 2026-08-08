from __future__ import annotations

from typing import Any

from .search_space import (
    CACHE_BUSTER_NONCE,
    OBJECTIVE_NAME,
    OBJECTIVE_UNIT,
    TOTAL_BUDGET,
    build_parameters,
)

DEFAULT_BACKEND = "auto"
DEFAULT_RANDOM_SEED = 20260730
DEFAULT_INITIAL_DESIGN_SIZE = 12
DEFAULT_BATCH_SIZE = 1


def build_intake(
    campaign_name: str,
    *,
    backend: str = DEFAULT_BACKEND,
    random_seed: int = DEFAULT_RANDOM_SEED,
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE,
) -> dict[str, Any]:
    return {
        "name": campaign_name,
        "description": (
            "Deterministic synthetic Ackley 6D benchmark under BO-MCP ownership. "
            f"Cache-buster nonce: {CACHE_BUSTER_NONCE}."
        ),
        "backend": backend,
        "batch_size": DEFAULT_BATCH_SIZE,
        "initial_design_size": initial_design_size,
        "max_observations": TOTAL_BUDGET,
        "random_seed": random_seed,
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }
