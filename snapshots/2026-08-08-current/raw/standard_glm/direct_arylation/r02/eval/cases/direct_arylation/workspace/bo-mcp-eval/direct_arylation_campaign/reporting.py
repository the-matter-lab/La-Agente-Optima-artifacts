"""Result recording and reporting for the direct arylation campaign.

All per-attempt records are appended to a local JSON artifact.
The BO-MCP server is the authority for campaign progress; this file
is append-only provenance for analysis and the final report.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


def _artifact_path(artifact_dir: str) -> str:
    os.makedirs(artifact_dir, exist_ok=True)
    return os.path.join(artifact_dir, "evaluation_log.jsonl")


def record_attempt(
    artifact_dir: str,
    *,
    attempt_index: int,
    parameter_values: dict[str, Any],
    status: str,
    objective_values: dict[str, float] | None = None,
    error: str | None = None,
    suggestion_id: str | None = None,
) -> dict:
    """Append one attempt record to the JSONL artifact and return it."""
    rec = {
        "attempt_index": attempt_index,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parameter_values": parameter_values,
        "status": status,
    }
    if objective_values is not None:
        rec["objective_values"] = objective_values
    if error is not None:
        rec["error"] = error
    if suggestion_id is not None:
        rec["suggestion_id"] = suggestion_id

    path = _artifact_path(artifact_dir)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def load_all_attempts(artifact_dir: str) -> list[dict]:
    """Read back all attempt records from the JSONL artifact."""
    path = _artifact_path(artifact_dir)
    if not os.path.exists(path):
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def print_summary(artifact_dir: str) -> str:
    """Print and return a human-readable summary of all attempts."""
    records = load_all_attempts(artifact_dir)
    total = len(records)
    successes = [r for r in records if r["status"] == "success"]
    failures = [r for r in records if r["status"] == "failed"]

    best_yield = None
    best_params = None
    for r in successes:
        y = r.get("objective_values", {}).get("yield")
        if y is not None and (best_yield is None or y > best_yield):
            best_yield = y
            best_params = r["parameter_values"]

    lines = [
        f"=== Campaign Summary ===",
        f"Total attempts: {total}",
        f"Successful:     {len(successes)}",
        f"Failed:         {len(failures)}",
    ]
    if best_yield is not None:
        lines.append(f"Best yield:     {best_yield:.2f}%")
        lines.append(f"Best params:    {best_params}")
    else:
        lines.append("Best yield:     N/A (no successful evaluations)")

    summary = "\n".join(lines)
    print(summary)
    return summary
