from typing import Any
from .search_space import get_parameters, get_objectives


def build_campaign_intake(campaign_name: str) -> dict[str, Any]:
    """Construct the campaign intake payload for BO-MCP.

    The campaign name must include the exact marker:
    akg-eval-a031fe657e2b4bd19101590d65050d1e
    """
    marker = "akg-eval-a031fe657e2b4bd19101590d65050d1e"
    if marker not in campaign_name:
        raise ValueError(f"Campaign name must contain the exact marker: {marker}")

    return {
        "name": campaign_name,
        "description": "Direct Arylation Benchmark Campaign",
        "parameters": get_parameters(),
        "objectives": get_objectives(),
        "backend": "auto",
    }
