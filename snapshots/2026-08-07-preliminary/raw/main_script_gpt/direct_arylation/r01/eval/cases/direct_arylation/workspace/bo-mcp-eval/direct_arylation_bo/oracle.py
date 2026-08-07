from __future__ import annotations

import os
from typing import Any

import requests


class OracleError(RuntimeError):
    """Raised when the direct-arylation oracle request fails."""


def evaluate_candidate(parameter_values: dict[str, Any], timeout_s: float = 60.0) -> float:
    base_url = os.environ["DIRECT_ARYLATION_API_URL"].rstrip("/")
    response = requests.post(
        f"{base_url}/v1/evaluate",
        json={
            "base": parameter_values["base"],
            "ligand": parameter_values["ligand"],
            "solvent": parameter_values["solvent"],
            "concentration": float(parameter_values["concentration"]),
            "temperature_c": int(parameter_values["temperature_c"]),
        },
        timeout=timeout_s,
    )
    if not response.ok:
        raise OracleError(f"oracle_http_{response.status_code}: {response.text[:300]}")
    payload = response.json()
    if "yield" not in payload:
        raise OracleError(f"oracle_missing_yield_key: {payload}")
    return float(payload["yield"])
