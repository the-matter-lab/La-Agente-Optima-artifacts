"""Search space: x_1..x_6 continuous in [0, 1]."""

DIM = 6
PARAM_NAMES = [f"x_{i}" for i in range(1, DIM + 1)]


def parameters() -> list[dict]:
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "Normalized Ackley coordinate (maps to z = -40 + 80*x).",
        }
        for name in PARAM_NAMES
    ]
