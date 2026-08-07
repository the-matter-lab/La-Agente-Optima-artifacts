# ackley_6d/search_space.py
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

def get_parameters():
    """
    Returns the search space parameters for the 6D Ackley optimization.
    Each parameter x_i is continuous on [0.0, 1.0].
    """
    return [
        {
            "name": f"x_{i}",
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0}
        }
        for i in range(1, 7)
    ]
