# Candidate evaluation module for direct arylation campaign
import os
import requests
import logfire

def evaluate_candidate(candidate: dict) -> dict:
    """
    Evaluate a single candidate against the direct arylation oracle.
    
    Parameters:
    - candidate: dict containing the exact five parameters:
      "base", "ligand", "solvent", "concentration", "temperature_c"
      
    Returns:
    - dict containing {"yield": float} if successful, or raises an exception.
    """
    base_url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not base_url:
        raise ValueError("DIRECT_ARYLATION_API_URL environment variable is not set.")
    
    url = f"{base_url.rstrip('/')}/v1/evaluate"
    
    # Ensure concentration and temperature_c are numeric
    payload = {
        "base": str(candidate["base"]),
        "ligand": str(candidate["ligand"]),
        "solvent": str(candidate["solvent"]),
        "concentration": float(candidate["concentration"]),
        "temperature_c": float(candidate["temperature_c"])
    }
    
    logfire.info("Evaluating candidate: {payload}", payload=payload)
    
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        logfire.error("Evaluation failed with status code {status_code}: {text}", 
                      status_code=response.status_code, text=response.text)
        response.raise_for_status()
        
    result = response.json()
    if "yield" not in result:
        raise ValueError(f"Invalid response from oracle: {result}")
        
    return result
