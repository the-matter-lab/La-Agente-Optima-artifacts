from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .intake import CAMPAIGN_MARKER, OBJECTIVE_NAME, USER_NONCE
from .search_space import PARAMETER_NAMES

CSV_COLUMNS = [
    "evaluation_index",
    "campaign_id",
    "suggestion_id",
    *PARAMETER_NAMES,
    OBJECTIVE_NAME,
    "status",
    "failure_reason",
    "raw_response",
    "classic",
]


def emit_tag(tag: str, payload: dict[str, Any]) -> None:
    print(f"[{tag}] {json.dumps(payload, sort_keys=True)}", flush=True)


def ensure_artifact_dir(root: str | Path, campaign_id: str) -> Path:
    path = Path(root) / f"campaign_{campaign_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_campaign_ref(artifact_dir: Path, *, campaign_id: str, campaign_name: str) -> None:
    payload = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "campaign_marker": CAMPAIGN_MARKER,
        "user_nonce": USER_NONCE,
    }
    (artifact_dir / "campaign_ref.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (artifact_dir / "campaign_id.txt").write_text(f"{campaign_id}\n")


def append_evaluation_row(artifact_dir: Path, row: dict[str, Any]) -> None:
    jsonl_path = artifact_dir / "evaluations.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")

    csv_path = artifact_dir / "evaluations.csv"
    needs_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(flatten_row(row))


def flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        "evaluation_index": row.get("evaluation_index"),
        "campaign_id": row.get("campaign_id"),
        "suggestion_id": row.get("suggestion_id"),
        OBJECTIVE_NAME: row.get("objective_values", {}).get(OBJECTIVE_NAME),
        "status": row.get("status"),
        "failure_reason": row.get("failure_reason"),
        "raw_response": row.get("raw_response"),
        "classic": row.get("classic"),
    }
    flattened.update({name: row.get("parameter_values", {}).get(name) for name in PARAMETER_NAMES})
    return flattened
