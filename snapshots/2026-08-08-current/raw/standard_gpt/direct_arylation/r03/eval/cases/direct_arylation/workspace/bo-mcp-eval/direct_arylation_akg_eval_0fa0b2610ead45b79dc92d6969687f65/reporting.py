from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .search_space import (
    CHAT_TRACE_ID,
    MARKER,
    NONCE,
    OBJECTIVE_NAME,
    TOTAL_ATTEMPT_BUDGET,
    ordered_parameter_values,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_summary(campaign: dict[str, Any], results: list[dict[str, Any]], suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    suggestion_map = {item["suggestion_id"]: item for item in suggestions}
    successful_attempts: list[dict[str, Any]] = []
    failed_attempts: list[dict[str, Any]] = []

    for result in results:
        suggestion_id = result.get("suggestion_id")
        suggestion = suggestion_map.get(suggestion_id, {})
        successful_attempts.append(
            {
                "suggestion_id": suggestion_id,
                "status": "successful",
                "parameter_values": ordered_parameter_values(result["parameter_values"]),
                "objective_values": {OBJECTIVE_NAME: float(result["objective_values"][OBJECTIVE_NAME])},
                "iteration": suggestion.get("iteration"),
                "created_at": suggestion.get("created_at"),
            }
        )

    successful_ids = {item["suggestion_id"] for item in successful_attempts}
    for suggestion in suggestions:
        if suggestion.get("status") != "rejected":
            continue
        if suggestion["suggestion_id"] in successful_ids:
            continue
        failed_attempts.append(
            {
                "suggestion_id": suggestion["suggestion_id"],
                "status": "failed",
                "parameter_values": ordered_parameter_values(suggestion["parameter_values"]),
                "iteration": suggestion.get("iteration"),
                "created_at": suggestion.get("created_at"),
            }
        )

    all_attempts = successful_attempts + failed_attempts
    all_attempts.sort(key=lambda item: (item.get("iteration") or 0, item.get("created_at") or "", item["suggestion_id"]))

    best = None
    if successful_attempts:
        best_attempt = max(successful_attempts, key=lambda item: item["objective_values"][OBJECTIVE_NAME])
        best = {
            "parameter_values": best_attempt["parameter_values"],
            "objective_values": best_attempt["objective_values"],
            "suggestion_id": best_attempt["suggestion_id"],
        }

    return {
        "marker": MARKER,
        "nonce": NONCE,
        "chat_trace_id": CHAT_TRACE_ID,
        "campaign_id": campaign["id"],
        "campaign_name": campaign["name"],
        "campaign_status": campaign["status"],
        "attempt_budget": TOTAL_ATTEMPT_BUDGET,
        "attempted_evaluations": len(all_attempts),
        "successful_evaluations": len(successful_attempts),
        "failed_evaluations": len(failed_attempts),
        "best": best,
        "attempts": all_attempts,
        "generated_at": utc_now_iso(),
    }
