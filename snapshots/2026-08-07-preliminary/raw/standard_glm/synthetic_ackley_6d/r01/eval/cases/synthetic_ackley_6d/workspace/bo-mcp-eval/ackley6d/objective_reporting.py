"""Objective extraction, result-row construction, and reporting for the 6D Ackley campaign."""

import csv
import json
import os
from datetime import datetime, timezone

from ackley6d.search_space import PARAM_NAMES


def build_result_row(
    *,
    evaluation_index: int,
    suggestion_id: str,
    parameter_values: dict[str, float],
    evaluator_output: dict | None,
    status: str,
    failure_reason: str | None = None,
) -> dict:
    """Build a BO-MCP result submission row and an artifact row.

    Returns (submit_row, artifact_row).
    """
    if status == "success" and evaluator_output is not None:
        objective_values = {"surface_response": evaluator_output["surface_response"]}
        raw_response = evaluator_output.get("raw_response")
    else:
        objective_values = {"surface_response": 0.0}
        raw_response = None

    submit_row = {
        "suggestion_id": suggestion_id,
        "parameter_values": parameter_values,
        "objective_values": objective_values,
    }

    artifact_row = {
        "evaluation_index": evaluation_index,
        "parameter_values": {k: parameter_values.get(k) for k in PARAM_NAMES},
        "objective_values": objective_values,
        "status": status,
        "failure_reason": failure_reason or "",
        "raw_response": raw_response,
    }
    return submit_row, artifact_row


def append_artifact(artifact_path: str, row: dict) -> None:
    """Append one row to the JSONL artifact file."""
    os.makedirs(os.path.dirname(artifact_path) or ".", exist_ok=True)
    with open(artifact_path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def write_results_csv(artifact_path: str, csv_path: str) -> int:
    """Convert JSONL artifact to CSV. Returns row count."""
    rows = []
    with open(artifact_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        return 0

    # Flatten for CSV
    flat_rows = []
    for r in rows:
        flat = {
            "evaluation_index": r["evaluation_index"],
            "status": r["status"],
            "failure_reason": r.get("failure_reason", ""),
            "raw_response": r.get("raw_response", ""),
            "surface_response": r["objective_values"]["surface_response"],
        }
        for k, v in r["parameter_values"].items():
            flat[k] = v
        flat_rows.append(flat)

    fieldnames = (
        ["evaluation_index"]
        + [f"x_{i}" for i in range(1, 7)]
        + ["surface_response", "status", "failure_reason", "raw_response"]
    )
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)

    return len(flat_rows)


def compute_summary(rows: list[dict]) -> dict:
    """Compute the end-of-campaign summary from artifact rows."""
    successful = [r for r in rows if r["status"] == "success"]
    attempted = len(rows)

    best = None
    if successful:
        best_row = max(successful, key=lambda r: r["objective_values"]["surface_response"])
        best = {
            "best_parameter_values": best_row["parameter_values"],
            "best_raw_response": best_row.get("raw_response"),
            "best_surface_response": best_row["objective_values"]["surface_response"],
        }

    return {
        "n_attempted": attempted,
        "n_successful": len(successful),
        "n_failed": attempted - len(successful),
        **(best or {}),
    }
