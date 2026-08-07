"""Search-space definition for the 6-D Ackley benchmark."""

SEARCH_SPACE = {
    "parameters": [
        {"name": f"x_{i}", "type": "continuous", "bounds": {"lower": 0.0, "upper": 1.0}}
        for i in range(1, 7)
    ],
}