"""Campaign intake construction for the direct-arylation benchmark.

Builds the immutable intake payload from the search-space definition.
"""

from __future__ import annotations

from direct_arylation_benchmark.search_space import PARAMETERS

CAMPAIGN_MARKER = "akg-eval-4177a21e5ec54adb9b46a50c81885888"


def build_intake(*, campaign_name: str) -> dict:
    """Return the campaign intake dict for BO-MCP.

    ``campaign_name`` must embed the invocation marker
    ``akg-eval-4177a21e5ec54adb9b46a50c81885888``.
    """
    return {
        "name": campaign_name,
        "description": (
            "Direct arylation reaction-yield optimization — "
            "5-parameter fully-crossed categorical/discrete search space "
            "(1,728 combinations). 60-evaluation budget, table-lookup oracle."
        ),
        "objectives": [
            {
                "name": "yield",
                "direction": "maximize",
                "unit": "percent",
            }
        ],
        "parameters": PARAMETERS,
        "batch_size": 1,
        "initial_design_size": 12,
"acquisition_method": "expected_improvement",
        "backend": "auto",
        # Do NOT set max_iterations / max_observations — the CLI budget
        # controls this invocation; a fossilized cap would prevent resume.
    }