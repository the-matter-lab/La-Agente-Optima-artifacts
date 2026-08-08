# direct_arylation_bo/intake.py
"""Build the BO-MCP campaign intake payload.

Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab
"""

from __future__ import annotations

from direct_arylation_bo.search_space import (
    BASES,
    CONCENTRATIONS,
    LIGANDS,
    SOLVENTS,
    TEMPERATURES_C,
)

CAMPAIGN_NAME = "direct-arylation-yield-akg-eval-d3d9f204a8d647dab3dc82339c33dc70"


def build_intake() -> dict:
    """Return the campaign intake dict for BO-MCP."""
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "BO optimisation of direct arylation reaction yield over a "
            "fully crossed 5-parameter search space (1728 candidates). "
            "Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab"
        ),
        "objectives": [
            {
                "name": "yield",
                "direction": "maximize",
                "unit": "%",
            }
        ],
        "parameters": [
            {
                "name": "base",
                "type": "categorical",
                "categories": list(BASES),
            },
            {
                "name": "ligand",
                "type": "categorical",
                "categories": list(LIGANDS),
            },
            {
                "name": "solvent",
                "type": "categorical",
                "categories": list(SOLVENTS),
            },
            {
                "name": "concentration",
                "type": "discrete",
                "values": list(CONCENTRATIONS),
            },
            {
                "name": "temperature_c",
                "type": "discrete",
                "values": list(TEMPERATURES_C),
            },
        ],
        "initial_design_size": 12,
        "batch_size": 1,
"backend": "baybe",
        # No max_iterations / max_observations — the CLI budget of 60
        # attempts governs this invocation; the campaign stays resumable.
    }