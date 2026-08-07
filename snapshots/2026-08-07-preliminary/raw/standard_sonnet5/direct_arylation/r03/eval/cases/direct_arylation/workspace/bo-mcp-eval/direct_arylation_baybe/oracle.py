"""Oracle evaluator: the only source of yield measurements for this campaign.

Reads the base URL exclusively from DIRECT_ARYLATION_API_URL (never
hardcoded, never inferred). Any non-2xx response, transport error, or
malformed body counts as a failed attempted evaluation -- it still
consumes one unit of the attempt budget.
"""
import os

import requests

REQUIRED_KEYS = ("base", "ligand", "solvent", "concentration", "temperature_c")


def evaluate_candidate(params: dict, *, timeout_s: float = 60.0) -> dict:
    base_url = os.environ.get("DIRECT_ARYLATION_API_URL", "").rstrip("/")
    if not base_url:
        return {"status": "failed", "yield": None, "http_status": None,
                 "error": "DIRECT_ARYLATION_API_URL is not set"}

    body = {k: params[k] for k in REQUIRED_KEYS}
    url = f"{base_url}/v1/evaluate"

    try:
        resp = requests.post(url, json=body, timeout=timeout_s)
    except requests.RequestException as exc:
        return {"status": "failed", "yield": None, "http_status": None, "error": str(exc)}

    if not (200 <= resp.status_code < 300):
        return {"status": "failed", "yield": None, "http_status": resp.status_code,
                 "error": resp.text[:500]}

    try:
        data = resp.json()
        yield_value = float(data["yield"])
    except (ValueError, KeyError, TypeError) as exc:
        return {"status": "failed", "yield": None, "http_status": resp.status_code,
                 "error": f"malformed oracle response body: {exc}"}

    return {"status": "success", "yield": yield_value, "http_status": resp.status_code, "error": None}
