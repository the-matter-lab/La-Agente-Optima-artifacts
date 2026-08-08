import math

from .search_space import PARAMETER_NAMES

RAW_MIN = -22.350402387287602
RAW_MAX = 0.0


def evaluate_ackley(parameter_values: dict[str, float]) -> dict:
    x = {name: float(parameter_values[name]) for name in PARAMETER_NAMES}
    if any(not 0.0 <= value <= 1.0 for value in x.values()):
        raise ValueError("all normalized coordinates must lie in [0.0, 1.0]")

    z = [-40.0 + 80.0 * x[name] for name in PARAMETER_NAMES]
    d = len(z)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(value * value for value in z) / d))
        - math.exp(sum(math.cos(2.0 * math.pi * value) for value in z) / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - RAW_MIN) / (RAW_MAX - RAW_MIN)
    if not math.isfinite(surface_response):
        raise ValueError("surface_response is not finite")
    return {
        "parameter_values": x,
        "raw_response": raw_response,
        "surface_response": surface_response,
    }
