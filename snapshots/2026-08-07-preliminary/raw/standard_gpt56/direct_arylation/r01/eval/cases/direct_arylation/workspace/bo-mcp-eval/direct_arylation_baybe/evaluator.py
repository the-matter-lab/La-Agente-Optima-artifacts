import math
import os
from dataclasses import dataclass

import requests

ORACLE_PATH = "/v1/evaluate"
PARAMETER_NAMES = ("base", "ligand", "solvent", "concentration", "temperature_c")


@dataclass(frozen=True)
class Evaluation:
    status: str
    objective_value: float | None
    http_status: int | None
    error: str | None
    response_excerpt: str | None


def evaluate_candidate(parameters: dict, timeout_s: float) -> Evaluation:
    base_url = os.environ.get("DIRECT_ARYLATION_API_URL")
    if not base_url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is required")
    payload = {name: parameters[name] for name in PARAMETER_NAMES}
    try:
        response = requests.post(
            base_url.rstrip("/") + ORACLE_PATH,
            json=payload,
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        return Evaluation("failed", None, None, f"{type(exc).__name__}: {exc}", None)

    excerpt = response.text[:1000]
    if not 200 <= response.status_code < 300:
        return Evaluation("failed", None, response.status_code, "non-2xx oracle response", excerpt)
    try:
        value = float(response.json()["yield"])
    except (ValueError, TypeError, KeyError, requests.JSONDecodeError) as exc:
        return Evaluation("failed", None, response.status_code, f"invalid oracle response: {exc}", excerpt)
    if not math.isfinite(value):
        return Evaluation("failed", None, response.status_code, "oracle yield is not finite", excerpt)
    return Evaluation("success", value, response.status_code, None, excerpt)
