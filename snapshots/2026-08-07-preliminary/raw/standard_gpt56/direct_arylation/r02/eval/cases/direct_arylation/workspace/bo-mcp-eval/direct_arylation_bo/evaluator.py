"""Oracle-only candidate evaluation; no benchmark table or local surrogate access."""

import math
import os
from typing import Any

import requests

PARAMETER_NAMES = ("base", "ligand", "solvent", "concentration", "temperature_c")


def evaluate_candidate(parameter_values: dict[str, Any], *, timeout_s: float) -> dict:
    base_url = os.environ.get("DIRECT_ARYLATION_API_URL")
    if not base_url:
        return {"status": "failed", "error": "DIRECT_ARYLATION_API_URL is not set"}

    body = {name: parameter_values[name] for name in PARAMETER_NAMES}
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/v1/evaluate",
            json=body,
            timeout=timeout_s,
        )
        if not response.ok:
            return {
                "status": "failed",
                "error": f"oracle HTTP {response.status_code}",
            }
        payload = response.json()
        value = payload["yield"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("response yield is not numeric")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("response yield is not finite")
        return {"status": "successful", "yield": value}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        return {"status": "failed", "error": str(exc)}
