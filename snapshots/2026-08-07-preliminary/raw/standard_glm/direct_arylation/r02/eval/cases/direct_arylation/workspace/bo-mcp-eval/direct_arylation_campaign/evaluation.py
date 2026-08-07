"""Oracle evaluation for the direct arylation benchmark.

Calls the external oracle at ``DIRECT_ARYLATION_API_URL`` and returns
the measured yield.  A non-2xx response counts as a failed attempt.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_ORACLE_TIMEOUT_S = 30.0


def _oracle_base_url() -> str:
    url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is not set")
    return url.rstrip("/")


def evaluate_candidate(parameter_values: dict[str, Any]) -> dict:
    """Evaluate a single candidate against the direct-arylation oracle.

    Returns a dict with keys:
      ``parameter_values`` — the exact five-name dict sent to the oracle
      ``status``           — ``"success"`` or ``"failed"``
      ``objective_values`` — ``{"yield": <float>}`` on success, absent on failure
      ``error``            — error detail string on failure, absent on success
    """
    # Build the payload with exact parameter names and values.
    # Categorical params (base, ligand, solvent) are sent as strings.
    # Discrete numeric params (concentration, temperature_c) are sent as
    # JSON numbers — the oracle expects numeric values, not strings.
    _NUMERIC_KEYS = {"concentration", "temperature_c"}
    payload = {}
    for key in ("base", "ligand", "solvent", "concentration", "temperature_c"):
        val = parameter_values.get(key)
        if val is None:
            return {
                "parameter_values": parameter_values,
                "status": "failed",
                "error": f"Missing parameter: {key}",
            }
        if key in _NUMERIC_KEYS:
            payload[key] = float(val)
        else:
            payload[key] = str(val)

    base_url = _oracle_base_url()
    url = f"{base_url}/v1/evaluate"

    try:
        resp = requests.post(url, json=payload, timeout=_ORACLE_TIMEOUT_S)
    except requests.RequestException as exc:
        return {
            "parameter_values": parameter_values,
            "status": "failed",
            "error": f"Request exception: {exc}",
        }

    if resp.status_code < 200 or resp.status_code >= 300:
        return {
            "parameter_values": parameter_values,
            "status": "failed",
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
        }

    try:
        body = resp.json()
    except ValueError:
        return {
            "parameter_values": parameter_values,
            "status": "failed",
            "error": f"Non-JSON response: {resp.text[:200]}",
        }

    # The oracle returns {"yield": <float>}.  Use explicit key check
    # (not ``or``) because 0.0 is a valid yield value.
    yield_val = None
    if isinstance(body, dict) and "yield" in body:
        yield_val = body["yield"]
    elif isinstance(body, dict) and "yield_percent" in body:
        yield_val = body["yield_percent"]
    elif isinstance(body, dict) and "result" in body:
        yield_val = body["result"]
    elif isinstance(body, (int, float)):
        yield_val = float(body)

    if yield_val is None:
        return {
            "parameter_values": parameter_values,
            "status": "failed",
            "error": f"No yield in response: {str(body)[:200]}",
        }

    return {
        "parameter_values": parameter_values,
        "status": "success",
        "objective_values": {"yield": float(yield_val)},
    }
