"""BO-MCP campaign intake for the Ackley-6D BayBE benchmark.

Backend, seed, initialization, batch schedule and acquisition strategy are
chosen fresh here (not copied from any prior run):
  - backend: baybe (explicitly pinned, per task requirement)
  - random_seed: 20240917
  - initial_design_size: 12 (2x dimensionality Sobol/random warmup)
  - batch_size: 6 (matches dimensionality; 60/6 = 10 total batches)
  - acquisition: upper_confidence_bound, beta=2.0 (extra exploration for the
    multimodal Ackley surface within a tight 60-evaluation budget)

`max_iterations`/`max_observations` are deliberately left unset: the intake
is immutable and the 60-evaluation budget is enforced by the campaign loop
(campaign.py), not fossilized into the spec.
"""

from .objective import OBJECTIVE_NAME, OBJECTIVE_UNIT
from .search_space import build_parameters

OWNERSHIP_MARKER = "akg-eval-01a2bebdff8c40379a2fd4b6ab495231"
CAMPAIGN_NAME = f"ackley6d-baybe-surface-response-{OWNERSHIP_MARKER}"

RANDOM_SEED = 20240917
INITIAL_DESIGN_SIZE = 12
BATCH_SIZE = 6
ACQUISITION_METHOD = "upper_confidence_bound"
ACQUISITION_BETA = 2.0


def build_intake() -> dict:
    assert OWNERSHIP_MARKER in CAMPAIGN_NAME
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Controlled synthetic benchmark: deterministic 6D Ackley surface "
            "mapped to a normalized [0,1] maximize objective 'surface_response'. "
            "No chemistry/experimental evaluator is used."
        ),
        "backend": "baybe",
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
        "batch_size": BATCH_SIZE,
        "initial_design_size": INITIAL_DESIGN_SIZE,
        "acquisition_method": ACQUISITION_METHOD,
        "acquisition_beta": ACQUISITION_BETA,
        "random_seed": RANDOM_SEED,
    }
