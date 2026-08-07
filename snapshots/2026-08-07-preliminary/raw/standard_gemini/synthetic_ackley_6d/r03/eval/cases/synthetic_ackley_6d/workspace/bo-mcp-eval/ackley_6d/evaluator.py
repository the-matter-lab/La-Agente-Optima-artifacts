# ackley_6d/evaluator.py
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

import math
from typing import Dict, Any, Tuple

def evaluate_ackley_6d(parameter_values: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """
    Evaluates the Ackley synthetic surface in 6 normalized dimensions.
    
    Args:
        parameter_values: Dict containing keys 'x_1' through 'x_6' with float values in [0.0, 1.0].
        
    Returns:
        Tuple of (success, results_dict, failure_reason)
        where results_dict contains 'surface_response' and 'raw_response' if success is True.
    """
    try:
        # Extract and validate parameters
        z_list = []
        for i in range(1, 7):
            key = f"x_{i}"
            if key not in parameter_values:
                return False, {}, f"Missing parameter {key}"
            
            val = parameter_values[key]
            if not isinstance(val, (int, float)):
                return False, {}, f"Parameter {key} is not a number: {val}"
            
            if not (0.0 <= val <= 1.0):
                return False, {}, f"Parameter {key} is out of bounds [0.0, 1.0]: {val}"
            
            # Map normalized x_i to z_i = -40 + 80 * x_i
            z_i = -40.0 + 80.0 * val
            z_list.append(z_i)
            
        d = 6.0
        sum_z_sq = sum(z ** 2 for z in z_list)
        sum_cos_z = sum(math.cos(2.0 * math.pi * z) for z in z_list)
        
        # Classic Ackley formula
        term1 = -20.0 * math.exp(-0.2 * math.sqrt(sum_z_sq / d))
        term2 = -math.exp(sum_cos_z / d)
        classic = term1 + term2 + 20.0 + math.e
        
        raw_response = -classic
        
        # Normalize surface_response
        # surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
        min_raw = -22.350402387287602
        max_raw = 0.0
        surface_response = (raw_response - min_raw) / (max_raw - min_raw)
        
        return True, {
            "surface_response": surface_response,
            "raw_response": raw_response
        }, ""
        
    except Exception as e:
        return False, {}, f"Unexpected error during evaluation: {str(e)}"
