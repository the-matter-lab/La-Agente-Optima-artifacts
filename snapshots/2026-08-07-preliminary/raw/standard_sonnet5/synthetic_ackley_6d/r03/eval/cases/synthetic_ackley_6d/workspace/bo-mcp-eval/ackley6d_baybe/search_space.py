"""Parameter search space for the 6D Ackley synthetic benchmark.

Six continuous, normalized dimensions x_1..x_6 on [0.0, 1.0].
"""

DIMENSIONS = 6
PARAMETER_NAMES = [f"x_{i}" for i in range(1, DIMENSIONS + 1)]


def build_parameters() -> list[dict]:
    """Return the BO-MCP `InputParameter` payloads for x_1..x_6."""
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "Normalized Ackley input dimension in [0.0, 1.0].",
        }
        for name in PARAMETER_NAMES
    ]
