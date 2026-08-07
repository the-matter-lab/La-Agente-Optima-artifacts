from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib import error, request

from .space import Candidate


@dataclass
class EvaluationResult:
    status: str
    objective_value: Optional[float]
    failure_reason: Optional[str]


class DirectArylationOracle:
    def __init__(self, base_url: Optional[str] = None, timeout_s: int = 30) -> None:
        self.base_url = (base_url or os.getenv("DIRECT_ARYLATION_API_URL", "")).rstrip("/")
        if not self.base_url:
            raise RuntimeError("DIRECT_ARYLATION_API_URL is not set")
        self.timeout_s = timeout_s

    def evaluate(self, candidate: Candidate) -> EvaluationResult:
        body = json.dumps(candidate.to_parameter_values()).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/v1/evaluate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            value = float(payload["yield"])
            return EvaluationResult(status="success", objective_value=value, failure_reason=None)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return EvaluationResult(
                status="failed",
                objective_value=None,
                failure_reason=f"HTTP {exc.code}: {detail[:300]}",
            )
        except Exception as exc:  # noqa: BLE001
            return EvaluationResult(
                status="failed",
                objective_value=None,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )


class MockOracle:
    """Synthetic oracle for smoke tests; does not call the benchmark service."""

    def evaluate(self, candidate: Candidate) -> EvaluationResult:
        key = json.dumps(candidate.to_parameter_values(), sort_keys=True)
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        value = round((int.from_bytes(digest[:4], "big") / (2**32 - 1)) * 100.0, 2)
        return EvaluationResult(status="success", objective_value=value, failure_reason=None)
