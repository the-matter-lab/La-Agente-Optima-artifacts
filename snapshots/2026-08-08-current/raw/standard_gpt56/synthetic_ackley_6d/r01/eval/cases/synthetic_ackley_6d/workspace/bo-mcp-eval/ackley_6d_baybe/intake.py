from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-51c1c165161b4a2c8d9e46348cddaf5c"
TOTAL_ATTEMPT_BUDGET = 60


def build_intake() -> dict:
    return {
        "name": f"{OWNERSHIP_MARKER}-ackley-6d-baybe",
        "description": "Controlled deterministic Ackley benchmark in six normalized dimensions.",
        "backend": "baybe",
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "random_seed": 26080551,
        "initial_design_size": 11,
        "batch_size": 4,
        "acquisition_method": "upper_confidence_bound",
        "acquisition_beta": 2.4,
        "max_observations": TOTAL_ATTEMPT_BUDGET,
    }
