"""Campaign-agnostic HTTP oracle evaluation harness (no campaign-specific imports)."""

from __future__ import annotations

import time
from typing import Any

import requests


def evaluate(
    payload: dict[str, Any],
    *,
    base_url: str,
    objective_name: str,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """POST one candidate to ``{base_url}/v1/evaluate`` and return an attempt record."""
    record: dict[str, Any] = {"parameter_values": payload, "status": "failed"}
    started = time.time()
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/v1/evaluate", json=payload, timeout=timeout_s
        )
        record["http_status"] = response.status_code
        if not response.ok:
            record["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
        else:
            value = response.json()[objective_name]
            record["objective_values"] = {objective_name: float(value)}
            record["status"] = "success"
    except Exception as exc:  # transport error, bad body, missing key
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["duration_s"] = round(time.time() - started, 3)
    return record
