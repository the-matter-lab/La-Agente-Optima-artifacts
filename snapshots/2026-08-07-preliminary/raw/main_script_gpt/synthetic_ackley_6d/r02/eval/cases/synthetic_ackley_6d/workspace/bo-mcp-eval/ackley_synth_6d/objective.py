from __future__ import annotations

from dataclasses import dataclass
import math

PARAMETER_NAMES = tuple(f"x_{i}" for i in range(1, 7))
ACKLEY_6D_RAW_MIN = -22.350402387287602
ACKLEY_6D_RAW_MAX = 0.0
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless"


@dataclass(frozen=True)
class AckleyEvaluation:
    parameter_values: dict[str, float]
    raw_response: float
    surface_response: float


def canonical_point(parameter_values: dict[str, float]) -> tuple[str, ...]:
    return tuple(format(float(parameter_values[name]), ".17g") for name in PARAMETER_NAMES)



def evaluate_ackley_6d(parameter_values: dict[str, float]) -> AckleyEvaluation:
    xs = [float(parameter_values[name]) for name in PARAMETER_NAMES]
    for idx, value in enumerate(xs, start=1):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"x_{idx}={value!r} is outside [0, 1]")
    zs = [-40.0 + 80.0 * value for value in xs]
    d = len(zs)
    classic = (
        -20.0 * math.exp(-0.2 * math.sqrt(sum(z * z for z in zs) / d))
        - math.exp(sum(math.cos(2.0 * math.pi * z) for z in zs) / d)
        + 20.0
        + math.e
    )
    raw_response = -classic
    surface_response = (raw_response - ACKLEY_6D_RAW_MIN) / (ACKLEY_6D_RAW_MAX - ACKLEY_6D_RAW_MIN)
    return AckleyEvaluation(
        parameter_values={name: float(parameter_values[name]) for name in PARAMETER_NAMES},
        raw_response=raw_response,
        surface_response=surface_response,
    )
