from __future__ import annotations

from datetime import UTC, datetime

from . import CACHE_BUSTER_NONCE, OBJECTIVE_NAME, OBJECTIVE_UNIT, OWNERSHIP_MARKER
from .search_space import parameter_definitions


def build_campaign_name(label: str | None = None) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = label or stamp
    return f"direct-arylation-{OWNERSHIP_MARKER}-{suffix}"


def build_intake(campaign_name: str, *, random_seed: int = 314159) -> dict:
    description = (
        "Direct arylation benchmark campaign. "
        f"ownership_marker={OWNERSHIP_MARKER}; cache_buster_nonce={CACHE_BUSTER_NONCE}. "
        "Fixed 1,728-point crossed search space, sequential BO, oracle-evaluated yield objective."
    )
    return {
        "name": campaign_name,
        "description": description,
        "backend": "auto",
        "batch_size": 1,
        "initial_design_size": 8,
        "acquisition_method": "noisy_expected_improvement",
        "random_seed": random_seed,
        "parameters": parameter_definitions(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }
