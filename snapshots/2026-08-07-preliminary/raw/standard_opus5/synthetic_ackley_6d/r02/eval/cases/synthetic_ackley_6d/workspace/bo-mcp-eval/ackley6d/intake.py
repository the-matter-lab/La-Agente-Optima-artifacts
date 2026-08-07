"""Campaign intake construction (immutable at creation time)."""

from . import MARKER
from .objective import OBJECTIVE_NAME, OBJECTIVE_UNIT
from .space import parameters

CAMPAIGN_NAME = f"ackley-6d-synthetic-surface-{MARKER}"


def build_intake(*, seed: int, batch_size: int, init_size: int, acquisition: str) -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Synthetic Ackley 6D benchmark. Normalized coordinates x_1..x_6 in [0,1] map to "
            "z = -40 + 80*x; surface_response is the min-max normalized negated classic Ackley."
        ),
        "parameters": parameters(),
        "objectives": [
            {"name": OBJECTIVE_NAME, "direction": "maximize", "unit": OBJECTIVE_UNIT}
        ],
        "backend": "baybe",
        "acquisition_method": acquisition,
        "batch_size": batch_size,
        "initial_design_size": init_size,
        "random_seed": seed,
    }
