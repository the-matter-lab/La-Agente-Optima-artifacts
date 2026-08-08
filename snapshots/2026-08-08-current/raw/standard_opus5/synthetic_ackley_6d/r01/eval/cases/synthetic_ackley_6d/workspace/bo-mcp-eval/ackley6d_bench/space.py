"""Search space: six continuous normalized dimensions x_1..x_6 in [0, 1]."""

DIM = 6
PARAM_NAMES = [f"x_{i}" for i in range(1, DIM + 1)]


def parameters() -> list[dict]:
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "normalized coordinate",
        }
        for name in PARAM_NAMES
    ]
