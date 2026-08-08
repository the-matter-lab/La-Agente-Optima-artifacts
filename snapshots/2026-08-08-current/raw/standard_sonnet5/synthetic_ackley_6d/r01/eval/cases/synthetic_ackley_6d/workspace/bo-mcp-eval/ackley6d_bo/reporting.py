"""Result artifact I/O and end-user reporting for the Ackley 6D campaign.

Artifact: one JSONL row per evaluated candidate (append-only, canonical),
mirrored into a CSV snapshot after every update for easy inspection.
Required per-row fields: evaluation_index, parameter_values, objective_values,
status, failure_reason (when failed), raw_response.
"""
import csv
import json
import os

from .search_space import PARAM_NAMES

FIELDNAMES = [
    "evaluation_index",
    "suggestion_id",
    *PARAM_NAMES,
    "surface_response",
    "raw_response",
    "status",
    "failure_reason",
]


def artifact_paths(artifact_dir: str, campaign_id: str) -> tuple[str, str]:
    os.makedirs(artifact_dir, exist_ok=True)
    base = os.path.join(artifact_dir, f"ackley6d_{campaign_id}")
    return f"{base}.jsonl", f"{base}.csv"


def load_rows(jsonl_path: str) -> list[dict]:
    if not os.path.exists(jsonl_path):
        return []
    rows = []
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_row(jsonl_path: str, csv_path: str, row: dict) -> None:
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(row) + "\n")
    rows = load_rows(jsonl_path)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            flat = {
                "evaluation_index": r.get("evaluation_index"),
                "suggestion_id": r.get("suggestion_id"),
                "surface_response": r.get("objective_values", {}).get("surface_response"),
                "raw_response": r.get("raw_response"),
                "status": r.get("status"),
                "failure_reason": r.get("failure_reason", ""),
                **r.get("parameter_values", {}),
            }
            writer.writerow(flat)


def make_row(evaluation_index: int, suggestion_id: str, parameter_values: dict, eval_result: dict) -> dict:
    row = {
        "evaluation_index": evaluation_index,
        "suggestion_id": suggestion_id,
        "parameter_values": parameter_values,
        "status": eval_result["status"],
    }
    if eval_result["status"] == "success":
        row["objective_values"] = {"surface_response": eval_result["surface_response"]}
        row["raw_response"] = eval_result["raw_response"]
    else:
        row["objective_values"] = {}
        row["failure_reason"] = eval_result.get("failure_reason", "unknown")
    return row


def summarize(rows: list[dict]) -> dict:
    successes = [r for r in rows if r.get("status") == "success"]
    n_attempted = len(rows)
    n_success = len(successes)
    best = None
    if successes:
        best = max(successes, key=lambda r: r["objective_values"]["surface_response"])
    return {
        "n_attempted": n_attempted,
        "n_success": n_success,
        "n_failed": n_attempted - n_success,
        "best_parameter_values": best["parameter_values"] if best else None,
        "best_raw_response": best["raw_response"] if best else None,
        "best_surface_response": best["objective_values"]["surface_response"] if best else None,
    }


def print_summary(summary: dict, campaign_id: str) -> None:
    print(f"[RESULT] campaign_id={campaign_id} attempted={summary['n_attempted']} "
          f"success={summary['n_success']} failed={summary['n_failed']}")
    if summary["best_parameter_values"] is not None:
        coords = ", ".join(f"{k}={v:.4f}" for k, v in summary["best_parameter_values"].items())
        print(f"[RESULT] best_surface_response={summary['best_surface_response']:.6f} "
              f"best_raw_response={summary['best_raw_response']:.6f}")
        print(f"[RESULT] best_coordinates: {coords}")
    else:
        print("[RESULT] no successful evaluations yet")
