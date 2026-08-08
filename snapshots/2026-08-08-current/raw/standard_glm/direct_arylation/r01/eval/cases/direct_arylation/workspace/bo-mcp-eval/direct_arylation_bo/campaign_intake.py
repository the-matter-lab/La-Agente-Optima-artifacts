"""Campaign intake construction for the direct-arylation benchmark."""

from __future__ import annotations

from direct_arylation_bo.search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-a2227614c6494db5ad4327686c34e5d2"


def build_intake(*, campaign_name: str | None = None) -> dict:
    """Return the BO-MCP campaign intake dict.

    Design choices:
    - Backend: ``baybe`` — supports mixed categorical + discrete spaces with
      192 categorical combinations (BoTorch caps at 100).
    - Batch size: 1 — sequential evaluation maximises information gain
      per evaluation under a tight 60-evaluation budget.
    - No ``max_iterations`` in intake — the CLI budget of 60 controls the
      invocation; the campaign stays resumable.
    """
    name = campaign_name or f"direct-arylation-{OWNERSHIP_MARKER}"
    return {
        "name": name,
        "description": (
            "Direct-arylation reaction-yield optimization. "
            f"Ownership marker: {OWNERSHIP_MARKER}"
        ),
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": "yield",
                "direction": "maximize",
            }
        ],
        "backend": "baybe",
        "batch_size": 1,
    }
