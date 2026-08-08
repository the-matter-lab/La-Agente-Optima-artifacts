"""Search-space definition for the 6D Ackley benchmark.

Six continuous parameters x_1..x_6, each in [0.0, 1.0].
"""

PARAM_NAMES = [f"x_{i}" for i in range(1, 7)]
PARAM_LOWER = 0.0
PARAM_UPPER = 1.0
DIM = 6


def build_parameters() -> list[dict]:
    """Return the BO-MCP intake ``parameters`` list."""
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": PARAM_LOWER, "upper": PARAM_UPPER},
        }
        for name in PARAM_NAMES
    ]
