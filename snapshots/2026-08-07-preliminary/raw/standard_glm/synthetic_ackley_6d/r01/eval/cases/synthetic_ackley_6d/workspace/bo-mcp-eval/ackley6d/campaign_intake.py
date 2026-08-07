"""Campaign intake construction for the 6D Ackley benchmark."""

from ackley6d.search_space import build_parameters

CAMPAIGN_MARKER = "akg-eval-08b0c2917b4f44cb9ab75ed75b9fdff9"


def build_intake(*, random_seed: int = 42) -> dict:
    """Return the full BO-MCP campaign intake dict.

    Key choices (not copied from prior runs):
    - backend: botorch (full feature set for continuous space)
    - acquisition: expected_improvement (classic, well-suited for 6D)
    - initial_design_size: 12 (2× dim, Sobol warmup)
    - batch_size: 1 (sequential, good for 60-eval budget)
    - random_seed: caller-chosen
    """
    return {
        "name": f"ackley6d-{CAMPAIGN_MARKER}",
        "description": (
            "6D Ackley synthetic benchmark. "
            f"Marker: {CAMPAIGN_MARKER}. "
            "Nonce: 20de70fe-0849-43d9-9827-c26fdd61729e"
        ),
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "backend": "botorch",
        "acquisition_method": "expected_improvement",
        "initial_design_size": 12,
        "batch_size": 1,
        "random_seed": random_seed,
    }
