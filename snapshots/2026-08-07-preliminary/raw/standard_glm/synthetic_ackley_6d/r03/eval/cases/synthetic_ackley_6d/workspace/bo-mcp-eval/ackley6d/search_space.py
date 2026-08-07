"""Search-space definition for the 6D Ackley benchmark.

Six continuous parameters x_1..x_6, each on [0, 1].
"""

DIM = 6
PARAM_NAMES = [f"x_{i}" for i in range(1, DIM + 1)]
LOWER = 0.0
UPPER = 1.0


def build_parameters() -> list[dict]:
    """Return the BO-MCP intake ``parameters`` list for the 6D Ackley space."""
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": LOWER, "upper": UPPER},
        }
        for name in PARAM_NAMES
    ]
