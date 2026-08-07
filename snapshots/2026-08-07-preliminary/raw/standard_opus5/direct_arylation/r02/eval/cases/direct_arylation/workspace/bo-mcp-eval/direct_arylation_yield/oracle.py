"""Candidate evaluation against the documented oracle endpoint.

POST ${DIRECT_ARYLATION_API_URL}/v1/evaluate with the exact candidate payload.
No other endpoint, table, or data source is consulted.
"""

import os

import requests

EVALUATE_PATH = "/v1/evaluate"


def endpoint() -> str:
    base = os.environ.get("DIRECT_ARYLATION_API_URL")
    if not base:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is not set")
    return base.rstrip("/") + EVALUATE_PATH


def evaluate(candidate: dict, *, objective_name: str, timeout_s: float = 120.0) -> dict:
    """Return {"status": "success"|"failed", "value": float|None, "error": str|None}."""
    try:
        response = requests.post(endpoint(), json=candidate, timeout=timeout_s)
        response.raise_for_status()
        payload = response.json()
        value = float(payload[objective_name])
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"non-finite {objective_name}: {value}")
    except Exception as exc:  # transport, HTTP, payload, or parsing failure
        return {"status": "failed", "value": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "success", "value": value, "error": None}
