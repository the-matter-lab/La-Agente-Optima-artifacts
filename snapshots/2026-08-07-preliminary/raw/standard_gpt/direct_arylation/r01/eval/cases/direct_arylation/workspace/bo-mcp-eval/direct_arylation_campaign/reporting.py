from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import OBJECTIVE_NAME
from .search_space import normalize_parameter_values


ATTEMPTED_STATUSES = {"completed", "rejected"}


def ensure_artifact_dir(base_dir: Path, campaign_id: str) -> Path:
    artifact_dir = base_dir / campaign_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def append_attempt_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def attempted_count_from_suggestions(suggestions: list[dict[str, Any]]) -> int:
    return sum(1 for suggestion in suggestions if suggestion.get("status") in ATTEMPTED_STATUSES)


def build_summary(*, campaign: dict[str, Any], suggestions: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    result_by_suggestion_id = {
        row.get("suggestion_id"): row for row in results if row.get("suggestion_id")
    }
    evaluated_candidates: list[dict[str, Any]] = []
    best_record: dict[str, Any] | None = None
    for suggestion in suggestions:
        status = suggestion.get("status")
        if status not in ATTEMPTED_STATUSES:
            continue
        normalized = normalize_parameter_values(dict(suggestion.get("parameter_values") or {}))
        result_row = result_by_suggestion_id.get(suggestion.get("suggestion_id"))
        objective_values = None
        record_status = "failed"
        if result_row is not None:
            objective_values = {OBJECTIVE_NAME: float(result_row["objective_values"][OBJECTIVE_NAME])}
            record_status = "succeeded"
            if best_record is None or objective_values[OBJECTIVE_NAME] > best_record["objective_values"][OBJECTIVE_NAME]:
                best_record = {
                    "suggestion_id": suggestion.get("suggestion_id"),
                    "parameter_values": normalized,
                    "objective_values": objective_values,
                }
        evaluated_candidates.append(
            {
                "suggestion_id": suggestion.get("suggestion_id"),
                "status": record_status,
                "parameter_values": normalized,
                "objective_values": objective_values,
            }
        )
    evaluated_candidates.sort(key=lambda row: row["suggestion_id"] or "")
    return {
        "campaign_id": campaign["id"],
        "campaign_name": campaign["name"],
        "campaign_status": campaign["status"],
        "attempted_evaluation_count": len(evaluated_candidates),
        "successful_evaluation_count": sum(1 for row in evaluated_candidates if row["status"] == "succeeded"),
        "best_conditions": None if best_record is None else best_record["parameter_values"],
        "best_measured_yield": None if best_record is None else best_record["objective_values"][OBJECTIVE_NAME],
        "evaluated_candidates": evaluated_candidates,
    }


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
