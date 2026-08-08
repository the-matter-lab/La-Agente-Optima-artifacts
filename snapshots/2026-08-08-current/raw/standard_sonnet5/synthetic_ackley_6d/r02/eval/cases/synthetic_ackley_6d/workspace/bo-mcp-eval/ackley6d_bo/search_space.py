"""Search-space definition: six normalized continuous parameters x_1..x_6 in [0, 1]."""

PARAM_NAMES = [f"x_{i}" for i in range(1, 7)]


def build_parameters() -> list[dict]:
    """Return the BO-MCP InputParameter payload list for x_1..x_6 on [0.0, 1.0]."""
    return [
        {"name": name, "type": "continuous", "bounds": {"lower": 0.0, "upper": 1.0}}
        for name in PARAM_NAMES
    ]
