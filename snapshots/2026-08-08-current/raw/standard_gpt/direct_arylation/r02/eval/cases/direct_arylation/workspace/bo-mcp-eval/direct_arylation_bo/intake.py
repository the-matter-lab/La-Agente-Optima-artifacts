from __future__ import annotations

from .search_space import CAMPAIGN_NAME, MARKER, OBJECTIVE_NAME, OBJECTIVE_UNIT, build_parameters, search_space_size


def build_intake() -> dict[str, object]:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Direct arylation yield optimization over the fixed 1,728-point measured benchmark "
            f"with ownership marker {MARKER}. BayBE backend, single-candidate sequential BO, "
            "60 attempted evaluations requested at execution time."
        ),
        "backend": "baybe",
        "batch_size": 1,
        "initial_design_size": 12,
        "random_seed": 57752,
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


def validate_space() -> None:
    size = search_space_size()
    if size != 1728:
        raise ValueError(f"Expected 1728 candidates, found {size}")
