from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .intake import CHAT_TRACE_ID, OBJECTIVE_NAME


def ensure_artifact_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_summary(
    *,
    campaign: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None,
    invocation_attempts: int,
) -> dict[str, Any]:
    best_attempt = None
    best_yield = None
    submitted = 0
    for attempt in attempts:
        objective_values = attempt.get("objective_values") or {}
        if OBJECTIVE_NAME in objective_values:
            measured_yield = float(objective_values[OBJECTIVE_NAME])
            if best_yield is None or measured_yield > best_yield:
                best_yield = measured_yield
                best_attempt = attempt
        if attempt.get("status") == "submitted":
            submitted += 1
    return {
        "chat_trace_id": CHAT_TRACE_ID,
        "campaign_id": None if campaign is None else campaign.get("id"),
        "campaign_name": None if campaign is None else campaign.get("name"),
        "campaign_status": None if campaign is None else campaign.get("status"),
        "invocation_attempts": invocation_attempts,
        "attempted_evaluations": len(attempts),
        "successful_submissions": submitted,
        "best_measured_yield": best_yield,
        "best_conditions": None if best_attempt is None else best_attempt.get("parameter_values"),
        "best_attempt_status": None if best_attempt is None else best_attempt.get("status"),
        "attempts": attempts,
        "diagnostics": diagnostics,
    }
