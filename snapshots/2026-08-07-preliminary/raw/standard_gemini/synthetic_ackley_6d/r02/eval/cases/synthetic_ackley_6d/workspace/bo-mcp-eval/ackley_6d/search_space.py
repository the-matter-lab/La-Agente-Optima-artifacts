from typing import Any

def get_parameters() -> list[dict[str, Any]]:
    """
    Return the list of input parameters for the 6D Ackley search space.
    Each parameter is continuous with bounds [0.0, 1.0].
    """
    return [
        {
            "name": f"x_{i}",
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0}
        }
        for i in range(1, 7)
    ]
