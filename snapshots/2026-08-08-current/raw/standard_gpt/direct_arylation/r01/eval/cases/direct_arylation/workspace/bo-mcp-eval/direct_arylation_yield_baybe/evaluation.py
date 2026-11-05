from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from .intake import CHAT_TRACE_ID, OBJECTIVE_NAME
from .search_space import canonicalize_parameter_values


@dataclass
class EvaluationResult:
    status: str
    parameter_values: dict[str, Any]
    objective_values: dict[str, float] | None = None
    error: str | None = None
    oracle_status_code: int | None = None
    oracle_response_text: str | None = None


def evaluate_candidate(
    *,
    api_url: str,
    parameter_values: dict[str, Any],
    timeout_s: float,
    session: requests.Session | None = None,
) -> EvaluationResult:
    values = canonicalize_parameter_values(parameter_values)
    client = session or requests.Session()
    response = client.post(
        f"{api_url.rstrip('/')}/v1/evaluate",
        json=values,
        timeout=timeout_s,
    )
    if response.status_code // 100 != 2:
        return EvaluationResult(
            status="oracle_http_error",
            parameter_values=values,
            error=f"Oracle returned HTTP {response.status_code}",
            oracle_status_code=response.status_code,
            oracle_response_text=response.text[:1000],
        )
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        return EvaluationResult(
            status="oracle_parse_error",
            parameter_values=values,
            error=f"Oracle returned non-JSON response: {exc}",
            oracle_status_code=response.status_code,
            oracle_response_text=response.text[:1000],
        )
    measured_yield = payload.get(OBJECTIVE_NAME)
    if not isinstance(measured_yield, (int, float)):
        return EvaluationResult(
            status="oracle_parse_error",
            parameter_values=values,
            error=f"Oracle response missing numeric {OBJECTIVE_NAME!r}: {payload}",
            oracle_status_code=response.status_code,
            oracle_response_text=json.dumps(payload, sort_keys=True)[:1000],
        )
    return EvaluationResult(
        status="oracle_success",
        parameter_values=values,
        objective_values={OBJECTIVE_NAME: float(measured_yield)},
        oracle_status_code=response.status_code,
        oracle_response_text=json.dumps(payload, sort_keys=True)[:1000],
    )


def build_attempt_record(
    *,
    attempt_index: int,
    campaign_id: str,
    suggestion_id: str,
    evaluation: EvaluationResult,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "attempt_index": attempt_index,
        "campaign_id": campaign_id,
        "suggestion_id": suggestion_id,
        "chat_trace_id": CHAT_TRACE_ID,
        "status": evaluation.status,
        "parameter_values": evaluation.parameter_values,
    }
    if evaluation.objective_values is not None:
        record["objective_values"] = evaluation.objective_values
    if evaluation.error:
        record["error"] = evaluation.error
    if evaluation.oracle_status_code is not None:
        record["oracle_status_code"] = evaluation.oracle_status_code
    if evaluation.oracle_response_text is not None:
        record["oracle_response_text"] = evaluation.oracle_response_text
    return record
