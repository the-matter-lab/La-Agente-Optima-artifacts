from __future__ import annotations

from datetime import datetime, timezone

CAMPAIGN_MARKER = "akg-eval-6c34bf90d0b945098371e25f43d3e068"
CACHE_BUSTER_NONCE = "27f0273b-23c0-4eaa-b54a-59af8f3eae73"
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"
TOTAL_BUDGET = 60
DIMENSION = 6
PARAMETER_NAMES = [f"x_{i}" for i in range(1, DIMENSION + 1)]
ACKLEY_RAW_MIN = -22.350402387287602
DEFAULT_RANDOM_SEED = 271828
DEFAULT_INITIAL_DESIGN_SIZE = 9
DEFAULT_ACQUISITION_METHOD = "upper_confidence_bound"
DEFAULT_ACQUISITION_BETA = 0.2


def build_campaign_name(label: str | None = None) -> str:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label_part = f"-{label}" if label else ""
    return (
        f"ackley-6d-{CAMPAIGN_MARKER}{label_part}-"
        f"{CACHE_BUSTER_NONCE[:8]}-{suffix}"
    )


def build_intake(name: str, random_seed: int = DEFAULT_RANDOM_SEED) -> dict[str, object]:
    parameters = [
        {
            "name": parameter_name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "Normalized Ackley coordinate.",
        }
        for parameter_name in PARAMETER_NAMES
    ]
    objectives = [
        {
            "name": OBJECTIVE_NAME,
            "direction": "maximize",
            "unit": OBJECTIVE_UNIT,
        }
    ]
    return {
        "name": name,
        "description": (
            "Deterministic 6D normalized Ackley benchmark. "
            f"Marker={CAMPAIGN_MARKER}. Nonce={CACHE_BUSTER_NONCE}."
        ),
        "parameters": parameters,
        "objectives": objectives,
        "backend": "botorch",
        "batch_size": 1,
        "initial_design_size": DEFAULT_INITIAL_DESIGN_SIZE,
        "acquisition_method": DEFAULT_ACQUISITION_METHOD,
        "acquisition_beta": DEFAULT_ACQUISITION_BETA,
        "random_seed": random_seed,
        "max_observations": TOTAL_BUDGET,
    }
