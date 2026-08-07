from __future__ import annotations

import os
from typing import Any

import requests

from .search_space import OBJECTIVE_NAME, ordered_parameter_values


class OracleConfigurationError(RuntimeError):
    pass


def get_oracle_base_url() -> str:
    base_url = os.environ.get("DIRECT_ARYLATION_API_URL", "").strip()
    if not base_url:
        raise OracleConfigurationError("DIRECT_ARYLATION_API_URL is required.")
    return base_url.rstrip("/")


def evaluate_candidate(parameter_values: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    ordered_values = ordered_parameter_values(parameter_values)
    url = f"{get_oracle_base_url()}/v1/evaluate"
    try:
        response = requests.post(url, json=ordered_values, timeout=timeout_s)
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "parameter_values": ordered_values,
            "error": str(exc),
            "oracle_url": url,
        }

    if not response.ok:
        return {
            "status": "failed",
            "parameter_values": ordered_values,
            "error": response.text.strip()[:500] or f"HTTP {response.status_code}",
            "http_status": response.status_code,
            "oracle_url": url,
        }

    try:
        body = response.json()
        measured_yield = float(body[OBJECTIVE_NAME])
    except (ValueError, KeyError, TypeError) as exc:
        return {
            "status": "failed",
            "parameter_values": ordered_values,
            "error": f"Invalid oracle response: {exc}",
            "http_status": response.status_code,
            "oracle_url": url,
        }

    return {
        "status": "successful",
        "parameter_values": ordered_values,
        "objective_values": {OBJECTIVE_NAME: measured_yield},
        "http_status": response.status_code,
        "oracle_url": url,
    }
