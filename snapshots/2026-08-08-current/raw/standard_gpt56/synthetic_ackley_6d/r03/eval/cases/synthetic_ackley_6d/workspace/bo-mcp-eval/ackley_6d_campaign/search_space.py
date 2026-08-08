PARAMETER_NAMES = tuple(f"x_{i}" for i in range(1, 7))


def build_parameters() -> list[dict]:
    return [
        {"name": name, "type": "continuous", "bounds": {"lower": 0.0, "upper": 1.0}}
        for name in PARAMETER_NAMES
    ]
