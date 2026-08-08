from __future__ import annotations

from . import (
    CAMPAIGN_MARKER,
    DEFAULT_ACQUISITION_METHOD,
    DEFAULT_BATCH_SIZE,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_RANDOM_SEED,
)
from .search_space import build_objectives, build_parameters


def build_campaign_name(*, random_seed: int = DEFAULT_RANDOM_SEED) -> str:
    return f"ackley-6d-baybe-{CAMPAIGN_MARKER}-seed-{random_seed}"


def build_campaign_intake(
    *,
    random_seed: int = DEFAULT_RANDOM_SEED,
    batch_size: int = DEFAULT_BATCH_SIZE,
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE,
    acquisition_method: str = DEFAULT_ACQUISITION_METHOD,
) -> dict[str, object]:
    return {
        "name": build_campaign_name(random_seed=random_seed),
        "description": (
            "Synthetic 6D Ackley benchmark optimized through BO-MCP with the BayBE backend. "
            "Evaluation is a deterministic local Python function; no chemistry or lab evaluator is used."
        ),
        "backend": "baybe",
        "random_seed": random_seed,
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "acquisition_method": acquisition_method,
        "parameters": build_parameters(),
        "objectives": build_objectives(),
    }
