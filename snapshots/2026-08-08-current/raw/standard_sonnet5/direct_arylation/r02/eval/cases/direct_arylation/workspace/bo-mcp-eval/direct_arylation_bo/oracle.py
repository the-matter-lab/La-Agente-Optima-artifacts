"""Oracle evaluator: POST a single exact candidate to the direct-arylation API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .search_space import OBJECTIVE_NAME


@dataclass
class OracleOutcome:
    ok: bool
    value: float | None = None
    http_status: int | None = None
    error: str | None = None


def evaluate_candidate(
    parameter_values: dict[str, Any],
    *,
    base_url: str,
    cache_buster: str,
    timeout_s: float = 60.0,
) -> OracleOutcome:
    """POST one candidate to ``{base_url}/v1/evaluate``.

    Any non-2xx response, timeout, or malformed body is a failed attempted
    evaluation (still counts toward the attempt budget) — it is never
    retried here, so each call maps to exactly one attempt.
    """
    url = f"{base_url.rstrip('/')}/v1/evaluate"
    body = {k: parameter_values[k] for k in parameter_values}
    try:
        resp = requests.post(
            url,
            json=body,
            params={"_cb": cache_buster},
            headers={"X-Cache-Buster": cache_buster},
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        return OracleOutcome(ok=False, error=f"request error: {exc}")

    if not (200 <= resp.status_code < 300):
        return OracleOutcome(
            ok=False,
            http_status=resp.status_code,
            error=f"non-2xx response: {resp.status_code} {resp.text[:300]}",
        )

    try:
        data = resp.json()
        value = float(data[OBJECTIVE_NAME])
    except (ValueError, KeyError, TypeError) as exc:
        return OracleOutcome(
            ok=False,
            http_status=resp.status_code,
            error=f"malformed response body: {exc}",
        )

    return OracleOutcome(ok=True, value=value, http_status=resp.status_code)
