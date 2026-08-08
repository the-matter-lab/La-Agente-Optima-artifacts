"""Immutable BO-MCP campaign intake for the direct-arylation yield benchmark."""

from . import search_space

MARKER = "akg-eval-6d0e0c6f27e643e281edfabe22ebe90e"


def build_intake(name: str | None = None) -> dict:
    """Intake payload; `max_iterations` stays unset (budget is a CLI bound)."""
    campaign_name = name or f"direct-arylation-yield {MARKER}"
    if MARKER not in campaign_name:
        raise ValueError(f"campaign name must contain the marker {MARKER}")
    return {
        "name": campaign_name,
        "description": (
            "Direct arylation reaction-yield maximization over a fully crossed "
            "base / ligand / solvent / concentration / temperature grid, scored by "
            "the direct-arylation oracle service."
        ),
        "backend": "baybe",
        "parameters": search_space.parameters(),
        "objectives": search_space.objectives(),
        "batch_size": 1,
    }
