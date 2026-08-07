from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .search_space import OBJECTIVE_NAME, PARAMETER_NAMES

RESULTS_JSONL = "results.jsonl"
SUMMARY_JSON = "summary.json"
RUN_LOG = "run.log"
DIAGNOSTICS_JSON = "diagnostics.json"
CAMPAIGN_EXPORT_CSV = "campaign_export.csv"


def ensure_artifact_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def summarize_records(records: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(records)
    successes = [row for row in rows if row.get("status") == "submitted"]
    best = None
    if successes:
        best = max(
            successes,
            key=lambda row: float(row.get("objective_values", {}).get(OBJECTIVE_NAME, float("-inf"))),
        )
    summary = {
        "attempted_evaluations": len(rows),
        "successful_evaluations": len(successes),
        "best_parameter_values": best.get("parameter_values") if best else None,
        "best_raw_response": best.get("raw_response") if best else None,
        "best_surface_response": (
            best.get("objective_values", {}).get(OBJECTIVE_NAME) if best else None
        ),
        "records": rows,
    }
    return summary


def write_summary(path: Path, summary: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")


def format_parameter_values(parameter_values: dict[str, float]) -> str:
    return ", ".join(f"{name}={float(parameter_values[name]):.6f}" for name in PARAMETER_NAMES)
