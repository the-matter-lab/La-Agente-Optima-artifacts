"""BO-MCP campaign intake for the direct arylation yield benchmark."""

from __future__ import annotations

from . import search_space as ss

# Ownership marker: every campaign created by this invocation carries it.
CAMPAIGN_MARKER = "akg-eval-2805014a05614c938643d467cfb9d6ff"
# Cache-buster nonce, repeated in artifacts and the campaign description.
NONCE = "63564e1a-5ca5-4172-97e2-374479e19e77"

CAMPAIGN_NAME = f"direct-arylation-yield {CAMPAIGN_MARKER}"


def build_intake(*, batch_size: int = 1, initial_design_size: int = 6, random_seed: int = 2805) -> dict:
    """Immutable campaign intake.

    Design: BayBE backend on a purely discrete/categorical space; one-hot
    encoded categoricals, sequential (batch_size=1) suggestions so every
    measurement informs the next, a small space-filling warmup, and
    qLogNEI acquisition for a noisy experimental yield target.
    ``max_iterations``/``max_observations`` are deliberately left unset —
    the 60-evaluation budget is a per-invocation CLI budget, not a
    permanent campaign cap.
    """
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Maximize measured yield of a direct arylation reaction over the fixed "
            f"fully crossed benchmark space of {ss.SIZE} measured reactions. "
            f"Oracle: DIRECT_ARYLATION_API_URL /v1/evaluate. nonce={NONCE}"
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "acquisition_method": "noisy_expected_improvement",
        "initial_design_size": initial_design_size,
        "random_seed": random_seed,
        "objectives": [
            {
                "name": ss.OBJECTIVE_NAME,
                "target_mode": ss.OBJECTIVE_DIRECTION,
                "unit": ss.OBJECTIVE_UNIT,
            }
        ],
        "parameters": ss.parameters(),
    }
