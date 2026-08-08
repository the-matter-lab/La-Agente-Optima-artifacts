from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import requests

from .bo import Candidate


@dataclass
class EvaluationResult:
    status: str
    objective_values: dict[str, float] | None
    failure_reason: str | None


class DirectArylationOracle:
    def __init__(self, api_url: str | None, dry_run: bool = False, timeout_s: float = 20.0) -> None:
        self.api_url = api_url
        self.dry_run = dry_run
        self.timeout_s = timeout_s
        self.session = requests.Session()

    @staticmethod
    def _pseudo_yield(candidate: Candidate) -> float:
        payload = "|".join(str(v) for v in candidate.key()).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        value = int(digest[:8], 16) / 0xFFFFFFFF
        return round(5.0 + 90.0 * value, 2)

    def evaluate(self, candidate: Candidate) -> EvaluationResult:
        if self.dry_run:
            return EvaluationResult(
                status="success",
                objective_values={"yield": self._pseudo_yield(candidate)},
                failure_reason=None,
            )

        if not self.api_url:
            return EvaluationResult(
                status="failed",
                objective_values=None,
                failure_reason="DIRECT_ARYLATION_API_URL is not set",
            )

        url = f"{self.api_url.rstrip('/')}/v1/evaluate"
        try:
            response = self.session.post(url, json=candidate.to_parameter_values(), timeout=self.timeout_s)
        except requests.RequestException as exc:
            return EvaluationResult(status="failed", objective_values=None, failure_reason=f"request_error: {exc}")

        if not response.ok:
            message = response.text.strip()
            if len(message) > 200:
                message = message[:200] + "..."
            return EvaluationResult(
                status="failed",
                objective_values=None,
                failure_reason=f"http_{response.status_code}: {message}",
            )

        try:
            payload: dict[str, Any] = response.json()
            value = float(payload["yield"])
        except Exception as exc:
            return EvaluationResult(status="failed", objective_values=None, failure_reason=f"invalid_response: {exc}")

        return EvaluationResult(status="success", objective_values={"yield": value}, failure_reason=None)


def api_url_from_env() -> str | None:
    return os.getenv("DIRECT_ARYLATION_API_URL")
