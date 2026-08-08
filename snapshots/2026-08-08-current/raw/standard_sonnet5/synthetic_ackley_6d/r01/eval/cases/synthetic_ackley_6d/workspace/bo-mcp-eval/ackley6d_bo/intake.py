"""Campaign intake construction for the Ackley 6D benchmark.

Ownership marker (must appear in every created campaign's name):
    akg-eval-3135b72daeac4d50bbb8b8b099a7fc02
"""
from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-3135b72daeac4d50bbb8b8b099a7fc02"
CACHE_BUSTER_NONCE = "f62806c2-a95a-4a49-80eb-993714a47ac6"

# Chosen for this run: seed, initial design, batch, acquisition. Not copied
# from any prior campaign.
RANDOM_SEED = 733029
INITIAL_DESIGN_SIZE = 12
BATCH_SIZE = 6
ACQUISITION_METHOD = "upper_confidence_bound"
ACQUISITION_BETA = 2.0


def build_campaign_name(suffix: str = "") -> str:
    base = f"ackley6d-benchmark-{OWNERSHIP_MARKER}"
    return f"{base}-{suffix}" if suffix else base


def build_intake(name_suffix: str = "") -> dict:
    name = build_campaign_name(name_suffix)
    assert OWNERSHIP_MARKER in name  # never create a campaign without the marker
    return {
        "name": name,
        "description": (
            "Synthetic 6D Ackley maximization benchmark (surface_response, "
            f"normalized). cache_buster_nonce={CACHE_BUSTER_NONCE}"
        ),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "parameters": build_parameters(),
        "backend": "baybe",
        "batch_size": BATCH_SIZE,
        "initial_design_size": INITIAL_DESIGN_SIZE,
        "random_seed": RANDOM_SEED,
        "acquisition_method": ACQUISITION_METHOD,
        "acquisition_beta": ACQUISITION_BETA,
    }
