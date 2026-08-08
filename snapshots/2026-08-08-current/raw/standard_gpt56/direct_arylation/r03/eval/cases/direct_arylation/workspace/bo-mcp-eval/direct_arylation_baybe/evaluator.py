import os
from numbers import Real

import requests

from .search_space import normalize_candidate


class EvaluationFailure(RuntimeError):
    pass


def evaluate(candidate: dict, timeout_s: float) -> float:
    base_url = os.environ.get("DIRECT_ARYLATION_API_URL")
    if not base_url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is required")
    candidate = normalize_candidate(candidate)
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/v1/evaluate",
            json=candidate,
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        raise EvaluationFailure(f"oracle request failed: {exc}") from exc
    if not response.ok:
        raise EvaluationFailure(f"oracle returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise EvaluationFailure("oracle returned non-JSON content") from exc
    if set(payload) != {"yield"} or not isinstance(payload["yield"], Real) or isinstance(payload["yield"], bool):
        raise EvaluationFailure("oracle response must be exactly {'yield': <number>}")
    value = float(payload["yield"])
    if not 0.0 <= value <= 100.0:
        raise EvaluationFailure("oracle yield must be a finite percent in [0, 100]")
    return value
