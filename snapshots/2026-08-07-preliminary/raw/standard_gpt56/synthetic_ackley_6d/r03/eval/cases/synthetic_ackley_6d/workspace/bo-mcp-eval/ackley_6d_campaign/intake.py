from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-273a2e70abb14b06b243be3577879b18"
CACHE_BUSTER_NONCE = "6edf52a5-d114-4751-ac25-afe3937e8fbe"
CAMPAIGN_NAME = f"ackley-6d-baybe-{OWNERSHIP_MARKER}"


def build_intake() -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Deterministic normalized 6D Ackley benchmark. "
            f"Ownership marker: {OWNERSHIP_MARKER}. Cache-buster: {CACHE_BUSTER_NONCE}."
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
        "random_seed": 240826,
        "initial_design_size": 12,
        "batch_size": 4,
        "acquisition_method": "expected_improvement",
    }
