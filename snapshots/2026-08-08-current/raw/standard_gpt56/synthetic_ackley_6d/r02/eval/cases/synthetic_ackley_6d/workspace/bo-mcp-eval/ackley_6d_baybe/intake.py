from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-5a18fcbd34154c7bbe05fc17c80f2044"
CAMPAIGN_NAME = f"ackley-6d-baybe-{OWNERSHIP_MARKER}-seed-816271"


def build_intake() -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Controlled noiseless 6D normalized Ackley benchmark; ownership marker "
            f"{OWNERSHIP_MARKER}."
        ),
        "backend": "baybe",
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "random_seed": 816271,
        "initial_design_size": 12,
        "batch_size": 4,
        "acquisition_method": "expected_improvement",
    }
