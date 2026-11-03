from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .search_space import Candidate


@dataclass
class EvaluationResult:
    success: bool
    status: str
    objective_value: Optional[float]
    failure_reason: str | None = None


class DirectArylationOracle:
    def __init__(self, timeout_s: float = 20.0):
        base_url = os.getenv('DIRECT_ARYLATION_API_URL')
        if not base_url:
            raise RuntimeError('DIRECT_ARYLATION_API_URL is not set.')
        self.base_url = base_url.rstrip('/')
        self.timeout_s = timeout_s

    def evaluate(self, candidate: Candidate) -> EvaluationResult:
        payload = json.dumps(candidate.to_parameter_values()).encode('utf-8')
        req = urllib.request.Request(
            url=f'{self.base_url}/v1/evaluate',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode('utf-8')
            parsed = json.loads(body)
            value = float(parsed['yield'])
            return EvaluationResult(success=True, status='success', objective_value=value)
        except urllib.error.HTTPError as exc:
            reason = f'HTTP {exc.code}'
            try:
                detail = exc.read().decode('utf-8').strip()
                if detail:
                    reason = f'{reason}: {detail[:200]}'
            except Exception:
                pass
            return EvaluationResult(success=False, status='failed', objective_value=None, failure_reason=reason)
        except Exception as exc:
            return EvaluationResult(success=False, status='failed', objective_value=None, failure_reason=type(exc).__name__ + f': {exc}')
