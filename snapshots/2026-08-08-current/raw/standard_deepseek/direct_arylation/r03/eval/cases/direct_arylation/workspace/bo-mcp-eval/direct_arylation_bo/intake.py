"""Campaign-intake construction for the direct-arylation BO campaign."""

from __future__ import annotations

from direct_arylation_bo.search_space import PARAMETERS

CAMPAIGN_MARKER = "akg-eval-b288ac68d8794799b65df188a7ae4ea4"


def build_intake() -> dict:
    """Return the immutable BO-MCP campaign intake dict.

    ``max_observations`` is set to 60 — the hard budget for this
    invocation.  ``max_iterations`` is left unset so the campaign can
    be reopened later if needed.
    """
    return {
        "name": f"direct-arylation-yield-{CAMPAIGN_MARKER}",
        "description": (
            "Bayesian optimisation of measured yield for a direct arylation "
            "reaction.  Single-objective (maximise yield, %).  "
            "5-parameter fully categorical search space (1 728 combinations).  "
            "Oracle: POST /v1/evaluate table-lookup."
        ),
        "objectives": [
            {
                "name": "yield",
                "target_mode": "maximize",
                "unit": "%",
            }
        ],
        "parameters": PARAMETERS,
        "backend": "botorch",
"acquisition_method": "noisy_expected_improvement",
        "batch_size": 1,
        "initial_design_size": 10,
        "max_observations": 60,
        "random_seed": 42,
    }