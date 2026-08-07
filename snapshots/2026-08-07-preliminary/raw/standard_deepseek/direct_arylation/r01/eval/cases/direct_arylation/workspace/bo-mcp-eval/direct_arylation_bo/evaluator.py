# direct_arylation_bo/evaluator.py
"""Oracle evaluator for the direct arylation reaction.

Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class EvaluationResult:
    """Outcome of a single oracle evaluation."""

    candidate: dict[str, Any]
    success: bool
    yield_value: float | None = None
    error: str | None = None


class OracleEvaluator:
    """Thin client for the direct arylation yield oracle."""

    def __init__(self) -> None:
        base_url = os.getenv("DIRECT_ARYLATION_API_URL")
        if not base_url:
            raise RuntimeError(
                "DIRECT_ARYLATION_API_URL is not set; it must point at the "
                "direct arylation oracle API."
            )
        self._url = base_url.rstrip("/") + "/v1/evaluate"
        self._session = requests.Session()
        self._session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def evaluate(self, candidate: dict[str, Any]) -> EvaluationResult:
        """POST the candidate to the oracle and return the result."""
        try:
            resp = self._session.post(self._url, json=candidate, timeout=30)
        except requests.RequestException as exc:
            return EvaluationResult(
                candidate=candidate, success=False, error=str(exc)
            )

        if resp.status_code >= 400:
            return EvaluationResult(
                candidate=candidate,
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:500]}",
            )

        try:
            body = resp.json()
        except ValueError:
            return EvaluationResult(
                candidate=candidate,
                success=False,
                error=f"Non-JSON 2xx body: {resp.text[:500]}",
            )

        yield_value = body.get("yield")
        if yield_value is None:
            return EvaluationResult(
                candidate=candidate,
                success=False,
                error=f"Missing 'yield' in response: {body}",
            )

        return EvaluationResult(
            candidate=candidate, success=True, yield_value=float(yield_value)
        )