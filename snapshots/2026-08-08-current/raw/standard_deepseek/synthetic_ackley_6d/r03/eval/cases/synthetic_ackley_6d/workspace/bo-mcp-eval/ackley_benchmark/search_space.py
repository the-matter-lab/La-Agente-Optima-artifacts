"""Campaign intake definition for the 6D Ackley synthetic benchmark."""

CAMPAIGN_MARKER = "akg-eval-154cf4595f874983bf81ab79c7d27e0a"


def build_intake() -> dict:
    """Return the immutable campaign intake payload for the Ackley benchmark.

    Six continuous parameters x_1..x_6 in [0, 1], one maximize objective
    ``surface_response``.  No ``max_iterations`` / ``max_observations`` cap
    — the CLI invocation budget controls how many evaluations to attempt.
    """
    return {
        "name": f"ackley-6d-benchmark-{CAMPAIGN_MARKER}",
        "description": (
            "6D Ackley synthetic benchmark: maximize surface_response "
            "(normalized -Ackley mapped from [0,1]^6)."
        ),
        "backend": "baybe",
        "batch_size": 1,
        "parameters": [
            {
                "name": f"x_{i}",
                "type": "continuous",
                "bounds": {"lower": 0.0, "upper": 1.0},
            }
            for i in range(1, 7)
        ],
        "objectives": [
            {
                "name": "surface_response",
                "target_mode": "maximize",
                "unit": "normalized_unitless",
            }
        ],
    }