from .search_space import parameters

OWNERSHIP_MARKER = "akg-eval-e8a9b391b1564f8f980c0080973e4d66"
# Cache-buster nonce: 46a801bd-6a04-4619-85af-c43ea27b8591
CACHE_BUSTER = "46a801bd-6a04-4619-85af-c43ea27b8591"
CAMPAIGN_NAME = f"direct-arylation-yield-baybe-{OWNERSHIP_MARKER}-{CACHE_BUSTER}"


def build_intake() -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": "Direct arylation measured-yield benchmark; 1728-point crossed space.",
        "backend": "baybe",
        "parameters": parameters(),
        "objectives": [{"name": "yield", "direction": "maximize", "unit": "percent"}],
        "batch_size": 1,
        "initial_design_size": 12,
        "acquisition_method": "expected_improvement",
        "random_seed": 20250308,
    }
