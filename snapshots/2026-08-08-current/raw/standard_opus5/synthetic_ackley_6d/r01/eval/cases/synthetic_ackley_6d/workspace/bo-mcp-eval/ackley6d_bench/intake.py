"""Campaign intake construction (BayBE backend, single maximize objective)."""

from .objective import OBJECTIVE_DIRECTION, OBJECTIVE_NAME, OBJECTIVE_UNIT
from .space import parameters

CAMPAIGN_MARKER = "akg-eval-7f1274a8431e4c5d94a3b24374899d9e"
NONCE = "f42213a0-34a7-4c2a-bbef-8b4700e0fb91"

RANDOM_SEED = 20481
INITIAL_DESIGN_SIZE = 12
BATCH_SIZE = 4


def build_intake(name_suffix: str) -> dict:
    return {
        "name": f"ackley6d-synthetic-{CAMPAIGN_MARKER}-{name_suffix}",
        "description": (
            "Controlled synthetic benchmark: 6D Ackley surface, deterministic "
            f"objective, no chemistry evaluator. nonce={NONCE}"
        ),
        "backend": "baybe",
        "parameters": parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
        "batch_size": BATCH_SIZE,
        "initial_design_size": INITIAL_DESIGN_SIZE,
        "acquisition_method": "expected_improvement",
        "random_seed": RANDOM_SEED,
    }
