import math

from .search_space import PARAMETER_NAMES

RAW_MIN = -22.350402387287602


def evaluate(parameters: dict[str, float]) -> tuple[float, float]:
    x = [float(parameters[name]) for name in PARAMETER_NAMES]
    if any(value < 0.0 or value > 1.0 for value in x):
        raise ValueError("candidate coordinate outside [0, 1]")
    z = [-40.0 + 80.0 * value for value in x]
    d = len(z)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(value * value for value in z) / d))
        - math.exp(sum(math.cos(2.0 * math.pi * value) for value in z) / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - RAW_MIN) / (0.0 - RAW_MIN)
    return raw_response, surface_response
