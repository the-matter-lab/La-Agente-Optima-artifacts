from __future__ import annotations

import os
from typing import Any

import requests


class OracleError(RuntimeError):
    """Raised when the direct arylation oracle evaluation fails."""


class DirectArylationOracle:
    def __init__(self, base_url: str | None = None, timeout_s: float = 60.0) -> None:
        self.base_url = (base_url or os.environ.get("DIRECT_ARYLATION_API_URL") or "").rstrip("/")
        if not self.base_url:
            raise RuntimeError("DIRECT_ARYLATION_API_URL is required")
        self.timeout_s = timeout_s
        self.session = requests.Session()

    def evaluate(self, parameter_values: dict[str, Any]) -> float:
        url = f"{self.base_url}/v1/evaluate"
        response = self.session.post(url, json=parameter_values, timeout=self.timeout_s)
        if response.status_code // 100 != 2:
            body = response.text.strip()
            raise OracleError(f"HTTP {response.status_code}: {body[:500]}")
        payload = response.json()
        if "yield" not in payload:
            raise OracleError(f"Oracle response missing yield: {payload}")
        value = float(payload["yield"])
        return value
