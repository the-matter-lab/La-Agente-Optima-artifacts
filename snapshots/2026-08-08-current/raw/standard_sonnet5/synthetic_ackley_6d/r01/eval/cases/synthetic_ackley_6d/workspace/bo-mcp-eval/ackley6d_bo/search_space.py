"""Search-space definition for the 6D Ackley benchmark.

Six continuous, normalized parameters x_1..x_6 on [0.0, 1.0]. The mapping
to the Ackley function's native domain (z_i = -40 + 80 * x_i) lives in
objective.py, not here.
"""

N_DIMS = 6
PARAM_NAMES = [f"x_{i}" for i in range(1, N_DIMS + 1)]


def build_parameters() -> list[dict]:
    """Return the IntakeData `parameters` list."""
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
            "description": "Normalized Ackley input dimension",
        }
        for name in PARAM_NAMES
    ]
