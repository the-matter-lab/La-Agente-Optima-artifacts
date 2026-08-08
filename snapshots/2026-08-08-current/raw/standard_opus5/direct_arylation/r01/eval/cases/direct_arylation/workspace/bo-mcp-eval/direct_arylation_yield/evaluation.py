"""Campaign-agnostic oracle evaluation harness.

Evaluates one exact candidate against an HTTP oracle service:
``POST {base_url}/v1/evaluate`` with the parameter values as the JSON body,
expecting ``{"<objective_name>": <float>}``. Any non-2xx response, transport
error, or unusable payload is an attempted-but-failed evaluation: it still
consumes budget and must be recorded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests

EVALUATE_PATH = "/v1/evaluate"


@dataclass(frozen=True)
class Evaluation:
    status: str  # "success" | "failed"
    objective_value: float | None
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "success"


def evaluate(
    base_url: str,
    parameter_values: dict,
    *,
    objective_name: str,
    timeout_s: float = 120.0,
) -> Evaluation:
    url = base_url.rstrip("/") + EVALUATE_PATH
    try:
        response = requests.post(url, json=parameter_values, timeout=timeout_s)
    except requests.RequestException as exc:
        return Evaluation("failed", None, f"transport error: {exc}")

    if not response.ok:
        return Evaluation("failed", None, f"HTTP {response.status_code}: {response.text[:200]}")

    try:
        value = float(response.json()[objective_name])
    except (ValueError, TypeError, KeyError) as exc:
        return Evaluation("failed", None, f"unusable payload ({exc}): {response.text[:200]}")

    if not math.isfinite(value):
        return Evaluation("failed", None, f"non-finite {objective_name}: {value}")
    return Evaluation("success", value, "ok")
