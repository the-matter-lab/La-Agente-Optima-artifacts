"""Oracle evaluator for the direct-arylation benchmark.

Calls the external REST oracle at DIRECT_ARYLATION_API_URL/v1/evaluate.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_TIMEOUT_S = 30.0


def evaluate_candidate(params: dict[str, Any]) -> tuple[float | None, bool]:
    """Evaluate a single candidate against the oracle.

    Returns (yield_value, success).
    - On success: (yield_percent, True)
    - On failure: (None, False)
    """
    base_url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not base_url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is not set")

    url = f"{base_url.rstrip('/')}/v1/evaluate"

    # Build the JSON body with the exact five lowercase parameter names.
    # concentration and temperature_c must be numeric.
    body = {
        "base": params["base"],
        "ligand": params["ligand"],
        "solvent": params["solvent"],
        "concentration": float(params["concentration"]),
        "temperature_c": float(params["temperature_c"]),
    }

    try:
        resp = requests.post(url, json=body, timeout=_TIMEOUT_S)
        if resp.status_code < 200 or resp.status_code >= 300:
            return None, False
        data = resp.json()
        yield_val = data.get("yield")
        if yield_val is None:
            return None, False
        return float(yield_val), True
    except Exception:
        return None, False
