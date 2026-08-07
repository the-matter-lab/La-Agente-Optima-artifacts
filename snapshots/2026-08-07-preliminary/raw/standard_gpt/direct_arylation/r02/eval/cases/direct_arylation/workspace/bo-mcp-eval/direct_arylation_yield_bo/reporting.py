from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .search_space import CACHE_BUSTER_NONCE, OBJECTIVE_NAME


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summarize_attempts(campaign_id: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [item for item in attempts if item.get("status") == "submitted"]
    best = max(successful, key=lambda item: item["objective_value"], default=None)
    return {
        "cache_buster_nonce": CACHE_BUSTER_NONCE,
        "campaign_id": campaign_id,
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successful),
        "failed_evaluations": len(attempts) - len(successful),
        "best_measured_yield": None if best is None else best["objective_value"],
        "best_conditions": None if best is None else best["candidate"],
        "objective_name": OBJECTIVE_NAME,
        "evaluated_candidates": attempts,
    }
