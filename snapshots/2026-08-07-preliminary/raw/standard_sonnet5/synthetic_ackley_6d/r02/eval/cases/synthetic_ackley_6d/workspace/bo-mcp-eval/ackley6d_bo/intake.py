"""Campaign intake construction (BayBE backend, single maximize objective)."""

from .search_space import build_parameters

MARKER = "akg-eval-23a9554a4f294e68a41175bde18c362a"
CAMPAIGN_NAME = f"ackley6d-baybe-{MARKER}"
OBJECTIVE_NAME = "surface_response"

# Heuristic warmup size for a 6-D continuous space: 2 * (d + 1).
DEFAULT_INITIAL_DESIGN_SIZE = 14
DEFAULT_BATCH_SIZE = 1


def build_intake(
    seed: int = 42,
    batch_size: int = DEFAULT_BATCH_SIZE,
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE,
) -> dict:
    """Build the immutable BO-MCP campaign intake payload.

    ``max_iterations``/``max_observations`` are deliberately left unset: the
    60-attempt budget is a CLI-level invocation/campaign budget enforced by
    the orchestrator against server-reported counts, not a fossilized cap on
    the (potentially reopened) campaign itself.
    """
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Deterministic synthetic Ackley-6D benchmark, BayBE backend, "
            f"marker={MARKER}."
        ),
        "backend": "baybe",
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "random_seed": seed,
    }
