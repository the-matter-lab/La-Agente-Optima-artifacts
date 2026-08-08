"""Result artifact and summary generation."""

from __future__ import annotations

import json
import os
from typing import Any


def build_artifact_row(
    *,
    eval_index: int,
    parameter_values: dict[str, float],
    surface_response: float | None,
    raw_response: float | None,
    status: str,
    failure_reason: str | None,
) -> dict[str, Any]:
    """Build one JSONL-serializable artifact row."""
    row: dict[str, Any] = {
        "evaluation_index": eval_index,
        "parameter_values": parameter_values,
        "objective_values": (
            {"surface_response": surface_response} if surface_response is not None else {}
        ),
        "status": status,
    }
    if failure_reason is not None:
        row["failure_reason"] = failure_reason
    if raw_response is not None:
        row["raw_response"] = raw_response
    return row


def write_artifact(artifact_dir: str, row: dict[str, Any]) -> None:
    """Append one row to the JSONL artifact file."""
    os.makedirs(artifact_dir, exist_ok=True)
    path = os.path.join(artifact_dir, "ackley_results.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def write_summary(
    artifact_dir: str,
    *,
    best_params: dict[str, float],
    best_raw_response: float,
    best_surface_response: float,
    attempted: int,
    successful: int,
    rows: list[dict[str, Any]],
) -> None:
    """Write the final summary JSON artifact."""
    os.makedirs(artifact_dir, exist_ok=True)

    summary = {
        "best_normalized_coordinates": best_params,
        "best_raw_response": best_raw_response,
        "best_surface_response": best_surface_response,
        "attempted_evaluations": attempted,
        "successful_evaluations": successful,
        "all_evaluations": rows,
    }

    path = os.path.join(artifact_dir, "ackley_summary.json")
    with open(path, "w") as f:
        json.dump(summary, f, indent=2)

    # Also write a human-readable table.
    table_path = os.path.join(artifact_dir, "ackley_table.txt")
    with open(table_path, "w") as f:
        f.write(f"{'idx':>4}  {'x_1':>8}  {'x_2':>8}  {'x_3':>8}  "
                f"{'x_4':>8}  {'x_5':>8}  {'x_6':>8}  "
                f"{'surface':>10}  {'raw':>10}  status\n")
        f.write("-" * 100 + "\n")
        for r in rows:
            pv = r.get("parameter_values", {})
            sr = r.get("objective_values", {}).get("surface_response", "")
            rr = r.get("raw_response", "")
            xs = "  ".join(f"{pv.get(f'x_{i}', 0.0):8.5f}" for i in range(1, 7))
            sr_str = f"{sr:10.6f}" if isinstance(sr, float) else f"{str(sr):>10}"
            rr_str = f"{rr:10.6f}" if isinstance(rr, float) else f"{str(rr):>10}"
            f.write(
                f"{r['evaluation_index']:4d}  {xs}  {sr_str}  {rr_str}  "
                f"{r['status']}\n"
            )
