from __future__ import annotations

from datetime import datetime, timezone

from .search_space import build_parameters

CAMPAIGN_MARKER = "akg-eval-88fef1120e594d599505287c7dd8ba7f"
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "normalized_unitless"
TOTAL_ATTEMPT_BUDGET = 60
USER_NONCE = "955b0c73-e93c-475f-b0fc-19ad0dfdc1ea"


def build_campaign_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"ackley-6d-{CAMPAIGN_MARKER}-{stamp}"


def build_campaign_description() -> str:
    return (
        "Synthetic deterministic Ackley 6D benchmark routed through BO-MCP. "
        f"Marker={CAMPAIGN_MARKER}. Nonce={USER_NONCE}."
    )


def build_intake() -> dict:
    return {
        "name": build_campaign_name(),
        "description": build_campaign_description(),
        "backend": "botorch",
        "random_seed": 20260730,
        "batch_size": 1,
        "initial_design_size": 12,
        "acquisition_method": "upper_confidence_bound",
        "acquisition_beta": 1.8,
        "max_observations": TOTAL_ATTEMPT_BUDGET,
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }
