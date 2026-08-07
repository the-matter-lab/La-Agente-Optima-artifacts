"""Oracle evaluation for direct arylation reaction yield."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import requests

from direct_arylation_campaign.search_space import candidate_to_oracle_payload, validate_candidate


class EvaluationError(Exception):
    """Raised when oracle evaluation fails."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def get_oracle_url() -> str:
    """Get the oracle API URL from environment."""
    url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not url:
        raise EvaluationError("DIRECT_ARYLATION_API_URL environment variable not set")
    return url.rstrip("/") + "/v1/evaluate"


def evaluate_candidate(candidate: dict[str, Any], timeout_s: float = 30.0) -> float:
    """
    Evaluate a single candidate via the oracle API.

    Args:
        candidate: Dict with base, ligand, solvent, concentration, temperature_c
        timeout_s: Request timeout in seconds

    Returns:
        Yield value as float (percent)

    Raises:
        EvaluationError: If evaluation fails (non-2xx, invalid response, etc.)
    """
    if not validate_candidate(candidate):
        raise EvaluationError(f"Invalid candidate parameters: {candidate}")

    payload = candidate_to_oracle_payload(candidate)
    url = get_oracle_url()

    # Generate idempotency key for this evaluation attempt
    idempotency_key = f"eval-{uuid.uuid4().hex[:12]}"
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }

    start = time.perf_counter()
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout_s)
        elapsed = time.perf_counter() - start
    except requests.Timeout:
        raise EvaluationError(f"Oracle request timed out after {timeout_s}s")
    except requests.RequestException as e:
        raise EvaluationError(f"Oracle request failed: {e}")

    if response.status_code >= 400:
        raise EvaluationError(
            f"Oracle returned {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )

    try:
        data = response.json()
    except ValueError:
        raise EvaluationError(f"Oracle returned non-JSON: {response.text[:500]}")

    if "yield" not in data:
        raise EvaluationError(f"Oracle response missing 'yield' field: {data}")

    yield_val = data["yield"]
    if not isinstance(yield_val, (int, float)):
        raise EvaluationError(f"Oracle yield is not numeric: {yield_val}")

    return float(yield_val)


def evaluate_batch(
    candidates: list[dict[str, Any]], timeout_s: float = 30.0
) -> list[dict[str, Any]]:
    """
    Evaluate a batch of candidates sequentially.

    Returns list of result dicts with:
    - candidate: the input candidate
    - yield: the yield value (float) or None if failed
    - status: "success" or "failed"
    - error: error message if failed
    - elapsed_s: evaluation time
    """
    results = []
    for candidate in candidates:
        start = time.perf_counter()
        try:
            yield_val = evaluate_candidate(candidate, timeout_s=timeout_s)
            elapsed = time.perf_counter() - start
            results.append({
                "candidate": candidate,
                "yield": yield_val,
                "status": "success",
                "error": None,
                "elapsed_s": elapsed,
            })
        except EvaluationError as e:
            elapsed = time.perf_counter() - start
            results.append({
                "candidate": candidate,
                "yield": None,
                "status": "failed",
                "error": str(e),
                "elapsed_s": elapsed,
            })
    return results