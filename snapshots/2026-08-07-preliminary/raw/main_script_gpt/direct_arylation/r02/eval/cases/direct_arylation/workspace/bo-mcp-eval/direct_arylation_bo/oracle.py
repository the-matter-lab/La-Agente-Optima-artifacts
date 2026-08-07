from __future__ import annotations

import os
from typing import Any

import requests


class DirectArylationOracleError(RuntimeError):
    """Raised when the direct-arylation oracle call fails."""


class DirectArylationOracle:
    def __init__(self, base_url: str | None = None, timeout_s: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("DIRECT_ARYLATION_API_URL", "")).rstrip("/")
        if not self.base_url:
            raise RuntimeError("DIRECT_ARYLATION_API_URL is required")
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def evaluate(self, parameter_values: dict[str, Any]) -> tuple[dict[str, float] | None, dict[str, Any]]:
        url = f"{self.base_url}/v1/evaluate"
        try:
            response = self.session.post(url, json=parameter_values, timeout=self.timeout_s)
        except requests.RequestException as exc:
            raise DirectArylationOracleError(str(exc)) from exc

        meta: dict[str, Any] = {
            "http_status": response.status_code,
            "response_text": response.text[:1000],
        }
        if not response.ok:
            return None, meta

        try:
            payload = response.json()
        except ValueError as exc:
            raise DirectArylationOracleError(f"Oracle returned non-JSON body: {response.text[:200]}") from exc

        if "yield" not in payload:
            raise DirectArylationOracleError(f"Oracle JSON missing 'yield': {payload}")
        meta["response_json"] = payload
        return {"yield": float(payload["yield"])}, meta
