from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from . import OBJECTIVE_NAME


class OracleEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OracleSuccess:
    measured_yield: float
    status_code: int


@dataclass(frozen=True)
class OracleFailure:
    status_code: int | None
    detail: str


def oracle_base_url() -> str:
    base_url = os.getenv("DIRECT_ARYLATION_API_URL", "").strip()
    if not base_url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is required")
    return base_url.rstrip("/")


def evaluate_candidate(parameter_values: dict[str, Any], *, timeout_s: float) -> OracleSuccess:
    response = requests.post(
        f"{oracle_base_url()}/v1/evaluate",
        json=parameter_values,
        timeout=timeout_s,
    )
    if not response.ok:
        raise OracleEvaluationError(
            f"oracle HTTP {response.status_code}: {response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OracleEvaluationError("oracle returned non-JSON body") from exc
    if set(payload) != {OBJECTIVE_NAME}:
        raise OracleEvaluationError(f"unexpected oracle payload keys: {sorted(payload)}")
    measured = payload[OBJECTIVE_NAME]
    if not isinstance(measured, (int, float)):
        raise OracleEvaluationError(f"oracle {OBJECTIVE_NAME} is not numeric: {measured!r}")
    return OracleSuccess(measured_yield=float(measured), status_code=response.status_code)
