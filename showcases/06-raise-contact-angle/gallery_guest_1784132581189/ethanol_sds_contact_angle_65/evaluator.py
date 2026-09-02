from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass
from typing import Any, Final

from domains.raise_platform.tools import run_raise_experiment

PENALTY_ANGLE_DEG = 180.0
MEASUREMENT_FAILURE_MARKERS: Final[tuple[str, ...]] = (
    "measurement failed",
    "contact angle measurement failed",
    "retry experiment",
    "non-finite static contact angle",
)


@dataclass
class EvaluationOutcome:
    candidate: dict[str, float]
    measured_angle: float | None
    submitted_angle: float | None
    success: bool
    error: str | None
    raw_result: dict[str, Any] | None
    retryable: bool
    outcome_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_candidate(candidate: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 6) for key, value in candidate.items()}


def within_target_window(angle: float, *, target: float, tolerance: float) -> bool:
    return target - tolerance <= angle <= target + tolerance


def _sanitize_error(exc: Exception) -> str:
    message = str(exc)
    if ", Traceback:" in message:
        message = message.split(", Traceback:", 1)[0]
    return message.strip()


def _coerce_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {
        "input_parameters": getattr(result, "input_parameters"),
        "static_contact_angle": getattr(result, "static_contact_angle"),
    }


def _normalize_echoed_inputs(
    observed: dict[str, Any], expected: dict[str, float]
) -> dict[str, float]:
    normalized = {key: float(value) for key, value in observed.items()}
    for key, expected_value in expected.items():
        if key not in normalized and math.isclose(expected_value, 0.0, abs_tol=1e-12):
            normalized[key] = 0.0
    return normalized


def _looks_like_measurement_failure(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in MEASUREMENT_FAILURE_MARKERS)


def evaluate_candidate(
    candidate: dict[str, float],
    *,
    timeout_s: int,
) -> EvaluationOutcome:
    normalized_candidate = normalize_candidate(candidate)
    try:
        raw_result = _coerce_result(
            asyncio.run(run_raise_experiment(normalized_candidate, timeout_s=timeout_s))
        )
        echoed_inputs = _normalize_echoed_inputs(
            raw_result.get("input_parameters") or {},
            normalized_candidate,
        )
        if set(echoed_inputs) != set(normalized_candidate):
            raise ValueError(
                f"RAISE echoed unexpected parameters: expected {sorted(normalized_candidate)}, "
                f"got {sorted(echoed_inputs)}"
            )
        for key, expected_value in normalized_candidate.items():
            if not math.isclose(echoed_inputs[key], expected_value, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError(
                    f"RAISE echoed mismatched {key}: expected {expected_value}, got {echoed_inputs[key]}"
                )
        measured_angle = float(raw_result["static_contact_angle"])
        if not math.isfinite(measured_angle):
            error = "RAISE returned a non-finite static contact angle."
            return EvaluationOutcome(
                candidate=normalized_candidate,
                measured_angle=None,
                submitted_angle=None,
                success=False,
                error=error,
                raw_result=raw_result,
                retryable=True,
                outcome_type="measurement_failure",
            )
        return EvaluationOutcome(
            candidate=normalized_candidate,
            measured_angle=measured_angle,
            submitted_angle=measured_angle,
            success=True,
            error=None,
            raw_result=raw_result,
            retryable=False,
            outcome_type="success",
        )
    except Exception as exc:
        error = _sanitize_error(exc)
        retryable = _looks_like_measurement_failure(error)
        return EvaluationOutcome(
            candidate=normalized_candidate,
            measured_angle=None,
            submitted_angle=None,
            success=False,
            error=error,
            raw_result=None,
            retryable=retryable,
            outcome_type="measurement_failure" if retryable else "evaluation_error",
        )

