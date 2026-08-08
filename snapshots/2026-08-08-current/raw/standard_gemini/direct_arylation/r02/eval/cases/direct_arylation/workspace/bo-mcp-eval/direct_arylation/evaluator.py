# direct_arylation/evaluator.py

import os
import requests
import logfire

def evaluate_candidate(candidate: dict, timeout_s: float = 30.0) -> dict | None:
    """Evaluate a single candidate against the direct arylation oracle.
    
    Reads the base URL from the environment variable DIRECT_ARYLATION_API_URL.
    Returns a dict with the measured objective value, e.g., {"yield": 78.95},
    or None if the evaluation failed (non-2xx response or connection error).
    """
    base_url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not base_url:
        raise ValueError("DIRECT_ARYLATION_API_URL environment variable is not set.")
        
    url = f"{base_url.rstrip('/')}/v1/evaluate"
    
    # Ensure correct types for discrete parameters
    payload = {
        "base": str(candidate["base"]),
        "ligand": str(candidate["ligand"]),
        "solvent": str(candidate["solvent"]),
        "concentration": float(candidate["concentration"]),
        "temperature_c": int(candidate["temperature_c"])
    }
    
    logfire.info("Evaluating candidate: {payload}", payload=payload)
    
    try:
        response = requests.post(url, json=payload, timeout=timeout_s)
        if response.status_code >= 200 and response.status_code < 300:
            result = response.json()
            logfire.info("Evaluation succeeded: {result}", result=result)
            return result
        else:
            logfire.error(
                "Evaluation failed with status code {status_code}: {text}",
                status_code=response.status_code,
                text=response.text
            )
            return None
    except Exception as e:
        logfire.error("Evaluation failed with exception: {error}", error=str(e))
        return None
