from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-32a412988ff64242ba3d82ec8e357298"
OBJECTIVE_NAME = "yield"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "percent"
BACKEND = "baybe"
CHAT_TRACE_ID = "e989e59e-6b70-4e48-88bf-388af427448f"
DEFAULT_INITIAL_DESIGN_SIZE = 12
DEFAULT_RANDOM_SEED = 1729


def build_campaign_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{OWNERSHIP_MARKER} direct-arylation-yield-baybe {timestamp}"


def build_campaign_description(max_attempts: int) -> str:
    return (
        "Direct arylation reaction yield optimization over a 1728-point measured search space "
        f"with BO-MCP backend={BACKEND}. Objective: maximize {OBJECTIVE_NAME} ({OBJECTIVE_UNIT}). "
        f"Per-invocation attempted-evaluation budget: {max_attempts}. "
        f"Chat trace: {CHAT_TRACE_ID}."
    )


def build_intake(*, max_attempts: int) -> dict[str, Any]:
    return {
        "name": build_campaign_name(),
        "description": build_campaign_description(max_attempts),
        "backend": BACKEND,
        "batch_size": 1,
        "initial_design_size": DEFAULT_INITIAL_DESIGN_SIZE,
        "random_seed": DEFAULT_RANDOM_SEED,
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


def ensure_owned_campaign(campaign: dict[str, Any]) -> None:
    name = str(campaign.get("name", ""))
    if OWNERSHIP_MARKER not in name:
        campaign_id = campaign.get("id", "<unknown>")
        raise ValueError(
            f"Refusing to use campaign {campaign_id!r} because name lacks ownership marker {OWNERSHIP_MARKER!r}."
        )
