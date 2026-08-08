# ackley_6d/intake.py
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

from .search_space import get_parameters


def get_intake(
    campaign_name: str,
    random_seed: int = 20260730,
    initial_design_size: int = 12,
    backend: str = "botorch",
):
    """
    Constructs the campaign intake payload for the Ackley 6D BO-MCP campaign.

    Chosen settings for this invocation:
    - backend: BoTorch
    - initialization strategy: space-filling Sobol warm start (BO-MCP/BoTorch default
      behavior for initial_design_size warmup points)
    - initial_design_size: 12
    - batch schedule: sequential, batch_size = 1
    - acquisition_method: expected_improvement_nonlog
    - random_seed: 20260730
    """
    ownership_marker = "akg-eval-43dcff3d628d4a86ba717e0455386a93"
    if ownership_marker not in campaign_name:
        campaign_name = f"{campaign_name} - {ownership_marker}"

    return {
        "name": campaign_name,
        "description": (
            "Synthetic 6D Ackley benchmark campaign. "
            "Nonce 54354cdc-4da6-4419-86a6-f4560fc0efbe."
        ),
        "backend": backend,
        "random_seed": random_seed,
        "initial_design_size": initial_design_size,
        "batch_size": 1,
        "acquisition_method": "expected_improvement_nonlog",
        "parameters": get_parameters(),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
    }
