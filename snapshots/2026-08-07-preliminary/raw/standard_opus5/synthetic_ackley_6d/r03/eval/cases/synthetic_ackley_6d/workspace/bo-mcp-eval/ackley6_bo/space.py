"""Search-space construction: 6 normalized continuous coordinates in [0, 1]."""

DIM = 6
PARAM_NAMES = [f"x_{i}" for i in range(1, DIM + 1)]


def parameters() -> list[dict]:
    """BO-MCP `InputParameter` payloads for the normalized Ackley-6 space."""
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "normalized coordinate, mapped to z = -40 + 80*x",
        }
        for name in PARAM_NAMES
    ]


def coords(parameter_values: dict) -> list[float]:
    """Ordered x_1..x_6 floats from a suggestion's parameter_values dict."""
    return [float(parameter_values[name]) for name in PARAM_NAMES]


def dedup_key(parameter_values: dict, decimals: int = 9) -> tuple:
    """Hashable identity of a point, used to never evaluate the same point twice."""
    return tuple(round(v, decimals) for v in coords(parameter_values))
