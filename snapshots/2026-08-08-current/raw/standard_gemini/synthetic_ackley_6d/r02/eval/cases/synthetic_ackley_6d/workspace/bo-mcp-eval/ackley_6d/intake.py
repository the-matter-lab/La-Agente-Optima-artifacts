from typing import Any
from ackley_6d.search_space import get_parameters

def get_campaign_intake(
    campaign_name: str,
    seed: int = 42,
    initial_design_size: int = 10,
    backend: str = "auto"
) -> dict[str, Any]:
    """
    Construct the campaign intake payload for BO-MCP.
    """
    # Ensure the campaign ownership marker is present in the name
    marker = "akg-eval-27628e9ae55a42e593594b0d8d0efe48"
    if marker not in campaign_name:
        campaign_name = f"{campaign_name}_{marker}"

    return {
        "name": campaign_name,
        "description": "Controlled synthetic benchmark over the Ackley function in 6 normalized dimensions.",
        "backend": backend,
        "random_seed": seed,
        "initial_design_size": initial_design_size,
        "batch_size": 1,
        "parameters": get_parameters(),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless"
            }
        ]
    }
