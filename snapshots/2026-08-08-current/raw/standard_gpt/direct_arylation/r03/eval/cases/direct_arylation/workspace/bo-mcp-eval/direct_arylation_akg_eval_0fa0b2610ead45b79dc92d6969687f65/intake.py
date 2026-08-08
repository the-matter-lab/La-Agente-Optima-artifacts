from __future__ import annotations

from .search_space import (
    CAMPAIGN_NAME,
    MARKER,
    NONCE,
    OBJECTIVE_DIRECTION,
    OBJECTIVE_NAME,
    OBJECTIVE_UNIT,
    SEARCH_PARAMETERS,
    TOTAL_ATTEMPT_BUDGET,
)


def build_intake() -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Direct arylation yield optimization benchmark. "
            f"marker={MARKER}; nonce={NONCE}; "
            "Oracle: DIRECT_ARYLATION_API_URL/v1/evaluate"
        ),
        "parameters": SEARCH_PARAMETERS,
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
        "batch_size": 1,
        "backend": "auto",
        "initial_design_size": 10,
        "max_observations": TOTAL_ATTEMPT_BUDGET,
        "random_seed": 20260730,
    }
