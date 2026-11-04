from __future__ import annotations

import os
import time
from typing import Any

import requests

from .search_space import OBJECTIVE_NAME


class EvaluationError(RuntimeError):
    pass


REQUIRED_KEYS = ("base", "ligand", "solvent", "concentration", "temperature_c")


def oracle_url() -> str:
    base_url = os.getenv("DIRECT_ARYLATION_API_URL", "").rstrip("/")
    if not base_url:
        raise EvaluationError("DIRECT_ARYLATION_API_URL is required")
    return f"{base_url}/v1/evaluate"


def normalise_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": candidate["base"],
        "ligand": candidate["ligand"],
        "solvent": candidate["solvent"],
        "concentration": float(candidate["concentration"]),
        "temperature_c": int(candidate["temperature_c"]),
    }


def evaluate_candidate(candidate: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    payload = normalise_candidate(candidate)
    started_at = time.time()
    try:
        response = requests.post(oracle_url(), json=payload, timeout=timeout_s)
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "candidate": payload,
            "error": f"request_exception: {exc}",
            "elapsed_s": round(time.time() - started_at, 3),
        }

    elapsed_s = round(time.time() - started_at, 3)
    if not response.ok:
        return {
            "status": "failed",
            "candidate": payload,
            "http_status": response.status_code,
            "error": response.text[:500],
            "elapsed_s": elapsed_s,
        }

    try:
        body = response.json()
    except ValueError as exc:
        return {
            "status": "failed",
            "candidate": payload,
            "http_status": response.status_code,
            "error": f"invalid_json: {exc}",
            "elapsed_s": elapsed_s,
        }

    value = body.get(OBJECTIVE_NAME)
    if not isinstance(value, (int, float)):
        return {
            "status": "failed",
            "candidate": payload,
            "http_status": response.status_code,
            "error": f"missing_numeric_{OBJECTIVE_NAME}",
            "response": body,
            "elapsed_s": elapsed_s,
        }

    return {
        "status": "success",
        "candidate": payload,
        OBJECTIVE_NAME: float(value),
        "http_status": response.status_code,
        "elapsed_s": elapsed_s,
    }
