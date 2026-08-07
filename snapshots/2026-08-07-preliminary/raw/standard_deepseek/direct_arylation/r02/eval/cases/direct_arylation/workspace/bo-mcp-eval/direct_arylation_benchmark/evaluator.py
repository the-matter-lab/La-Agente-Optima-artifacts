"""Oracle evaluator for the direct-arylation table-lookup benchmark.

Posts candidate reaction conditions to the oracle endpoint and returns
the measured yield.  Every call consumes one evaluation attempt.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests


class OracleError(RuntimeError):
    """The oracle rejected the request or returned an unexpected payload."""


def _oracle_base_url() -> str:
    url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not url:
        raise OracleError(
            "DIRECT_ARYLATION_API_URL is not set — cannot reach the yield oracle."
        )
    return url.rstrip("/")


def evaluate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one candidate against the direct-arylation yield oracle.

    Parameters
    ----------
    candidate : dict
        Must contain the five parameter keys: ``base``, ``ligand``,
        ``solvent``, ``concentration``, ``temperature_c``.
        ``concentration`` and ``temperature_c`` are sent as numbers.

    Returns
    -------
    dict
        ``{"yield": <float>, "status": "success"}`` on success, or
        ``{"status": "failed", "http_status": <int>, "detail": <str>}``
        on failure.
    """
    base_url = _oracle_base_url()
    url = f"{base_url}/v1/evaluate"

    # Build the request body — concentration and temperature_c must be numeric.
    body: dict[str, Any] = {
        "base": candidate["base"],
        "ligand": candidate["ligand"],
        "solvent": candidate["solvent"],
        "concentration": float(candidate["concentration"]),
        "temperature_c": float(candidate["temperature_c"]),
    }

    try:
        resp = requests.post(url, json=body, timeout=30)
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "http_status": None,
            "detail": f"Oracle request error: {exc}",
        }

    if resp.status_code < 200 or resp.status_code >= 300:
        return {
            "status": "failed",
            "http_status": resp.status_code,
            "detail": resp.text[:500],
        }

    try:
        payload = resp.json()
    except ValueError:
        return {
            "status": "failed",
            "http_status": resp.status_code,
            "detail": f"Non-JSON response: {resp.text[:500]}",
        }

    if "yield" not in payload or not isinstance(payload["yield"], (int, float)):
        return {
            "status": "failed",
            "http_status": resp.status_code,
            "detail": f"Unexpected response shape: {payload}",
        }

    return {"yield": float(payload["yield"]), "status": "success"}