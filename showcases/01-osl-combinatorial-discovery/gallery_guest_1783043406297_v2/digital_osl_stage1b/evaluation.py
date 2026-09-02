from __future__ import annotations

from dataclasses import fields
from typing import Any

from digital_osl_stage1.config import Stage1Config
from digital_osl_stage1.evaluation import (
    EvaluationResult,
    evaluate_candidate as _stage1_evaluate_candidate,
    evaluate_candidates as _stage1_evaluate_candidates,
    result_to_jsonable,
)

from .config import Stage1bConfig

_STAGE1_CONFIG_FIELDS = {field.name for field in fields(Stage1Config)}


def _coerce_stage1_config(config: Stage1bConfig | Stage1Config | dict[str, Any] | Any) -> Stage1Config:
    if isinstance(config, Stage1Config):
        return config.materialize()
    if hasattr(config, "to_jsonable_dict"):
        payload = config.to_jsonable_dict()
    elif isinstance(config, dict):
        payload = dict(config)
    else:
        payload = dict(vars(config))
    payload.pop("artifact_dir", None)
    filtered = {key: value for key, value in payload.items() if key in _STAGE1_CONFIG_FIELDS}
    return Stage1Config(**filtered).materialize()


def evaluate_candidate(
    candidate: dict[str, Any],
    config: Stage1bConfig | Stage1Config | dict[str, Any] | Any,
    suggestion_id: str | None = None,
) -> EvaluationResult:
    return _stage1_evaluate_candidate(candidate, _coerce_stage1_config(config), suggestion_id=suggestion_id)


def evaluate_candidates(
    candidates: list[dict[str, Any]],
    config: Stage1bConfig | Stage1Config | dict[str, Any] | Any,
) -> list[EvaluationResult]:
    return _stage1_evaluate_candidates(candidates, _coerce_stage1_config(config))


__all__ = [
    "EvaluationResult",
    "evaluate_candidate",
    "evaluate_candidates",
    "result_to_jsonable",
]
