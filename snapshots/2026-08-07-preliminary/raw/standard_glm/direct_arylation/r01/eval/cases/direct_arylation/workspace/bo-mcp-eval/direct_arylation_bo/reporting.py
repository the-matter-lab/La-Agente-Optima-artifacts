"""Objective extraction, artifact writing, and final reporting."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def make_attempt_record(
    *,
    attempt_index: int,
    suggestion_id: str,
    parameter_values: dict[str, Any],
    yield_value: float | None,
    success: bool,
) -> dict[str, Any]:
    """Build one standardized attempt record for the JSONL artifact."""
    record: dict[str, Any] = {
        "attempt_index": attempt_index,
        "suggestion_id": suggestion_id,
        "parameter_values": parameter_values,
        "status": "success" if success else "failed",
    }
    if success and yield_value is not None:
        record["objective_values"] = {"yield": yield_value}
    else:
        record["objective_values"] = None
    return record


def append_artifact(artifact_path: Path, record: dict[str, Any]) -> None:
    """Append one record to the JSONL artifact file."""
    with open(artifact_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def write_final_report(
    *,
    artifact_path: Path,
    campaign_id: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute and write the final summary report.

    Returns the summary dict (also printed as [RESULT]).
    """
    successful = [a for a in attempts if a["status"] == "success"]
    failed = [a for a in attempts if a["status"] == "failed"]

    best_yield = None
    best_params = None
    if successful:
        best = max(successful, key=lambda a: (a.get("objective_values") or {}).get("yield", float("-inf")))
        best_yield = best["objective_values"]["yield"]
        best_params = best["parameter_values"]

    summary = {
        "campaign_id": campaign_id,
        "total_attempted": len(attempts),
        "successful_evaluations": len(successful),
        "failed_evaluations": len(failed),
        "best_yield": best_yield,
        "best_conditions": best_params,
        "all_attempts": attempts,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    report_path = artifact_path.parent / "final_report.json"
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary
