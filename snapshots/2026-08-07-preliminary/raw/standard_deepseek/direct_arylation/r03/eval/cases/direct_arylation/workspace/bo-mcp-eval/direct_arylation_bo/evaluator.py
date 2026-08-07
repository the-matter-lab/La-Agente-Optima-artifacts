"""Oracle evaluator for the direct-arylation table-lookup API.

Calls ``POST ${DIRECT_ARYLATION_API_URL}/v1/evaluate`` and returns the
measured yield.  Non-2xx responses count as failed attempts.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests


class OracleError(Exception):
    """A failed oracle call (non-2xx or unparseable response)."""


def _api_url() -> str:
    url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not url:
        print(
            "[ALERT] DIRECT_ARYLATION_API_URL is not set — cannot call the oracle.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url.rstrip("/")


def evaluate_one(params: dict[str, Any]) -> dict[str, Any]:
    """Call the oracle for one candidate.

    Parameters
    ----------
    params : dict
        Must contain the five keys: ``base``, ``ligand``, ``solvent``,
        ``concentration``, ``temperature_c``.

    Returns
    -------
    dict
        ``{"yield": float}`` on success.

    Raises
    ------
    OracleError
        On any non-2xx response or unparseable body.
    """
    # Ensure concentration and temperature_c are numeric (BO-MCP may return
    # categorical values as strings).
    body = {
        "base": params["base"],
        "ligand": params["ligand"],
        "solvent": params["solvent"],
        "concentration": float(params["concentration"]),
        "temperature_c": int(float(params["temperature_c"])),
    }

    base = _api_url()
    try:
        resp = requests.post(
            f"{base}/v1/evaluate",
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise OracleError(f"Oracle request failed: {exc}") from exc

    if not resp.ok:
        raise OracleError(
            f"Oracle returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise OracleError(f"Oracle response is not valid JSON: {resp.text[:200]}") from exc

    if "yield" not in data:
        raise OracleError(f"Oracle response missing 'yield' key: {data}")

    return {"yield": float(data["yield"])}