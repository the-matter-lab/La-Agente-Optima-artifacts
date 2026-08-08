"""Search space and objective function for 6D Ackley benchmark."""

import math
from typing import Dict, List, Tuple

# Parameter names
PARAM_NAMES = [f"x_{i}" for i in range(1, 7)]

# Bounds for all parameters: [0.0, 1.0]
PARAM_BOUNDS = {name: (0.0, 1.0) for name in PARAM_NAMES}

# Ackley function constants
D = 6
A = 20.0
B = 0.2
C = 2.0 * math.pi
E = math.e

# Normalization constants (pre-computed for surface_response)
# raw_response range: [-22.350402387287602, 0.0]
RAW_RESPONSE_MIN = -22.350402387287602
RAW_RESPONSE_MAX = 0.0


def map_x_to_z(x_values: List[float]) -> List[float]:
    """Map x_i in [0,1] to z_i in [-40, 40]."""
    return [-40.0 + 80.0 * x for x in x_values]


def classic_ackley(z_values: List[float]) -> float:
    """Compute classic Ackley function value."""
    sum_sq = sum(z * z for z in z_values)
    sum_cos = sum(math.cos(C * z) for z in z_values)
    term1 = -A * math.exp(-B * math.sqrt(sum_sq / D))
    term2 = -math.exp(sum_cos / D)
    return term1 + term2 + A + E


def raw_response(x_values: List[float]) -> float:
    """Compute raw_response = -classic_ackley(z)."""
    z_values = map_x_to_z(x_values)
    classic = classic_ackley(z_values)
    return -classic


def surface_response(x_values: List[float]) -> float:
    """Compute normalized surface_response in [0, 1]."""
    raw = raw_response(x_values)
    return (raw - RAW_RESPONSE_MIN) / (RAW_RESPONSE_MAX - RAW_RESPONSE_MIN)


def evaluate_ackley_6d(x_values: List[float]) -> Dict[str, float]:
    """Evaluate the 6D Ackley function and return all metrics."""
    if len(x_values) != 6:
        raise ValueError(f"Expected 6 parameters, got {len(x_values)}")
    
    z_values = map_x_to_z(x_values)
    classic = classic_ackley(z_values)
    raw = -classic
    surface = (raw - RAW_RESPONSE_MIN) / (RAW_RESPONSE_MAX - RAW_RESPONSE_MIN)
    
    return {
        "z_values": z_values,
        "classic_ackley": classic,
        "raw_response": raw,
        "surface_response": surface,
    }


def get_parameter_bounds() -> List[Tuple[str, float, float]]:
    """Return list of (name, lower, upper) for all parameters."""
    return [(name, 0.0, 1.0) for name in PARAM_NAMES]