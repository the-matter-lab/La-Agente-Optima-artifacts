"""Campaign intake construction for the BayBE-backed benchmark."""

from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-5089117b4fee448dbfcb264fbba1cae7"
CACHE_BUSTER_NONCE = "98bbe2bd-bb9d-4442-bcb5-0e5f610ca86d"


def build_intake(*, smoke_test: bool = False) -> dict:
    suffix = "-smoke" if smoke_test else ""
    return {
        "name": f"direct-arylation-yield-{OWNERSHIP_MARKER}{suffix}",
        "description": (
            "Maximize measured direct arylation reaction yield (%). "
            f"Ownership marker: {OWNERSHIP_MARKER}. "
            f"Cache-buster nonce: {CACHE_BUSTER_NONCE}."
        ),
        "backend": "baybe",
        "parameters": build_parameters(),
        "objectives": [
            {"name": "yield", "direction": "maximize", "unit": "percent"}
        ],
        "acquisition_method": "expected_improvement",
        "initial_design_size": 12,
        "batch_size": 1,
        "random_seed": 5089117,
    }
