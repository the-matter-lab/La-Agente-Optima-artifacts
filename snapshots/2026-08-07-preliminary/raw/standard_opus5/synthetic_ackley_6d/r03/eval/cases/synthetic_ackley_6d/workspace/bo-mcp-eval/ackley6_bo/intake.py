"""Campaign intake construction (immutable once created)."""

from .objective import OBJECTIVE_DIRECTION, OBJECTIVE_NAME, OBJECTIVE_UNIT
from .space import parameters

MARKER = "akg-eval-2a04c50f6e2f4a42952ebc5cbc96b431"
NONCE = "c02de9f3-c0fa-4590-bebf-d77d7aa55ad1"

CAMPAIGN_NAME = f"ackley6-surface-response {MARKER}"

# Specialist-chosen strategy for this benchmark.
RANDOM_SEED = 31337
INIT_DESIGN_SIZE = 12  # 2*d space-filling warmup points
INIT_BATCH_SIZE = 6  # warmup batches: 2 x 6 = 12 points
BO_BATCH_SIZE = 6  # model-driven batches: 8 x 6 = 48 points (fewer, cheaper server fits)
ACQUISITION_METHOD = "upper_confidence_bound"
ACQUISITION_BETA = 2.0  # exploration weight, Ackley is strongly multi-modal


def build_intake() -> dict:
    """BO-MCP campaign intake for the Ackley-6 benchmark (BayBE backend)."""
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Synthetic Ackley benchmark in 6 normalized dimensions; deterministic, "
            f"noiseless evaluator. Traceability nonce {NONCE}."
        ),
        "parameters": parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": OBJECTIVE_DIRECTION,
                "unit": OBJECTIVE_UNIT,
            }
        ],
        "backend": "baybe",
        "batch_size": INIT_BATCH_SIZE,
        "initial_design_size": INIT_DESIGN_SIZE,
        "random_seed": RANDOM_SEED,
        "acquisition_method": ACQUISITION_METHOD,
        "acquisition_beta": ACQUISITION_BETA,
        # max_iterations / max_observations intentionally unset: the 60-evaluation
        # budget is a per-invocation CLI budget, not an immutable campaign cap.
    }


def batch_size_for(n_done: int, remaining: int) -> int:
    """Batch schedule: 6 per batch throughout (warmup and model-driven phase)."""
    planned = INIT_BATCH_SIZE if n_done < INIT_DESIGN_SIZE else BO_BATCH_SIZE
    return max(1, min(planned, remaining))
