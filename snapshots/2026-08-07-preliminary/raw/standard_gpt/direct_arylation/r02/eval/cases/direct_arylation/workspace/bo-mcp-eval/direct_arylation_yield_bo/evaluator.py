from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from .search_space import CACHE_BUSTER_NONCE, OBJECTIVE_NAME, canonical_candidate


@dataclass(slots=True)
class EvaluationFailure(Exception):
    message: str
    candidate: dict[str, Any]
    status_code: int | None = None
    response_text: str | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class EvaluationSuccess:
    candidate: dict[str, Any]
    objective_name: str
    objective_value: float
    response_payload: dict[str, Any]


def _trim(text: str, limit: int = 500) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3] + "..."


def evaluate_candidate(
    *,
    api_url: str,
    candidate: dict[str, Any],
    timeout_s: float,
    session: requests.Session | None = None,
) -> EvaluationSuccess:
    canonical = canonical_candidate(candidate)
    request_url = f"{api_url.rstrip('/')}/v1/evaluate"
    http = session or requests.Session()
    response = http.post(
        request_url,
        json=canonical,
        timeout=timeout_s,
        headers={
            "Content-Type": "application/json",
            "X-Cache-Buster-Nonce": CACHE_BUSTER_NONCE,
        },
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise EvaluationFailure(
            message=f"Oracle returned HTTP {response.status_code}.",
            candidate=canonical,
            status_code=response.status_code,
            response_text=_trim(response.text),
        )
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise EvaluationFailure(
            message="Oracle returned non-JSON success payload.",
            candidate=canonical,
            status_code=response.status_code,
            response_text=_trim(response.text),
        ) from exc
    if OBJECTIVE_NAME not in payload:
        raise EvaluationFailure(
            message=f"Oracle response is missing '{OBJECTIVE_NAME}'.",
            candidate=canonical,
            status_code=response.status_code,
            response_text=_trim(response.text),
        )
    try:
        objective_value = float(payload[OBJECTIVE_NAME])
    except (TypeError, ValueError) as exc:
        raise EvaluationFailure(
            message=f"Oracle response has non-numeric '{OBJECTIVE_NAME}'.",
            candidate=canonical,
            status_code=response.status_code,
            response_text=_trim(response.text),
        ) from exc
    return EvaluationSuccess(
        candidate=canonical,
        objective_name=OBJECTIVE_NAME,
        objective_value=objective_value,
        response_payload=payload,
    )
