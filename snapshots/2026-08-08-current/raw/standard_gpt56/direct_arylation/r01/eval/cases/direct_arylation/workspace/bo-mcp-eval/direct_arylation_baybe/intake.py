from .search_space import build_parameters

MARKER = "akg-eval-c5b8d1ef58b7491e871349ed99f9483b"
NONCE = "84b0bae8-8245-4434-aa84-be3c9ca05210"
CAMPAIGN_NAME = f"direct-arylation-yield-{MARKER}"
TOTAL_ATTEMPTS = 60


def build_intake() -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "BayBE optimization of measured direct arylation yield. "
            f"Ownership marker: {MARKER}. Cache-buster nonce: {NONCE}."
        ),
        "parameters": build_parameters(),
        "objectives": [{"name": "yield", "direction": "maximize", "unit": "percent"}],
        "backend": "baybe",
        "batch_size": 1,
        "max_iterations": TOTAL_ATTEMPTS,
        "random_seed": 20260805,
    }
