"""BO-MCP campaign intake for the direct arylation yield campaign (BayBE backend)."""

from . import space

MARKER = "akg-eval-1c094af49d534fef9861377f221f0f69"
CAMPAIGN_NAME = f"direct-arylation-yield-{MARKER}"


def build_intake(*, batch_size: int = 1, initial_design_size: int = 8, random_seed: int = 42) -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Direct arylation reaction-yield maximization over a fully crossed "
            "base x ligand x solvent x concentration x temperature grid (1,728 conditions), "
            "measured through the direct arylation oracle service."
        ),
        "objectives": [
            {
                "name": space.OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": space.OBJECTIVE_UNIT,
            }
        ],
        "parameters": space.parameters(),
        "backend": "baybe",
        "acquisition_method": "expected_improvement",
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "random_seed": random_seed,
        # max_iterations is deliberately unset: the attempt budget is a CLI budget.
    }
