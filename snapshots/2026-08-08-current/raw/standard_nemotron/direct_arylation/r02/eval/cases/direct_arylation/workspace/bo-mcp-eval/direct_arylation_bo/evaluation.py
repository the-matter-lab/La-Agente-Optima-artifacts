"""Oracle evaluation for the direct arylation benchmark."""

import os
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .search_space import validate_candidate


DEFAULT_TIMEOUT_SECONDS = 15.0


class OracleEvaluationError(RuntimeError):
    """Oracle evaluation failed for a candidate."""

    def __init__(self, message: str, candidate: dict[str, Any], status_code: int | None = None):
        super().__init__(message)
        self.candidate = candidate
        self.status_code = status_code


def get_oracle_base_url() -> str:
    """Get the oracle API base URL from environment."""
    url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not url:
        raise OracleEvaluationError(
            "DIRECT_ARYLATION_API_URL environment variable is required",
            candidate={},
        )
    return url.rstrip("/")


def evaluate_candidate(
    candidate: dict[str, Any],
    *,
    base_url: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """Evaluate a single candidate via the oracle API.

    Args:
        candidate: Dictionary with keys base, ligand, solvent, concentration, temperature_c
        base_url: Optional override for oracle base URL
        timeout_s: Request timeout in seconds

    Returns:
        Measured yield as float

    Raises:
        OracleEvaluationError: If evaluation fails (non-2xx, timeout, invalid response)
    """
    # Validate candidate structure
    if not validate_candidate(candidate):
        raise OracleEvaluationError(
            "Candidate contains invalid parameter values",
            candidate=candidate,
        )

    resolved_url = base_url or get_oracle_base_url()
    payload = {
        "base": candidate["base"],
        "ligand": candidate["ligand"],
        "solvent": candidate["solvent"],
        "concentration": candidate["concentration"],
        "temperature_c": candidate["temperature_c"],
    }

    request = Request(
        f"{resolved_url}/v1/evaluate",
        data=json.dumps(payload).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise OracleEvaluationError(
            f"Oracle returned HTTP {exc.code}: {detail}",
            candidate=candidate,
            status_code=exc.code,
        ) from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise OracleEvaluationError(
            f"Oracle request failed: {type(exc).__name__}: {exc}",
            candidate=candidate,
        ) from exc

    try:
        result: Any = json.loads(body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise OracleEvaluationError(
            "Oracle returned invalid JSON",
            candidate=candidate,
        ) from exc

    measured_yield = result.get("yield") if isinstance(result, dict) else None
    if not isinstance(measured_yield, (int, float)) or isinstance(measured_yield, bool):
        raise OracleEvaluationError(
            "Oracle response is missing numeric `yield`",
            candidate=candidate,
        )

    return float(measured_yield)


def evaluate_candidates_batch(
    candidates: list[dict[str, Any]],
    *,
    base_url: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Evaluate multiple candidates sequentially.

    Returns list of result dicts with keys:
    - candidate: the input candidate
    - yield: measured yield (float) on success
    - error: error message (str) on failure
    - status: "success" or "failed"
    """
    results = []
    for candidate in candidates:
        try:
            yield_val = evaluate_candidate(candidate, base_url=base_url, timeout_s=timeout_s)
            results.append({
                "candidate": candidate,
                "yield": yield_val,
                "error": None,
                "status": "success",
            })
        except OracleEvaluationError as exc:
            results.append({
                "candidate": candidate,
                "yield": None,
                "error": str(exc),
                "status": "failed",
            })
    return results