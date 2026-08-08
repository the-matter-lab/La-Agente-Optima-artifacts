"""Reporting utilities: result extraction, artifact writing, final summary."""

import json
import os
from datetime import datetime, timezone
from typing import Any


def extract_objective(eval_result: dict) -> dict[str, float]:
    """Extract the objective_values dict for BO-MCP submission."""
    return {"surface_response": eval_result["surface_response"]}


def build_result_row(
    evaluation_index: int,
    parameter_values: dict[str, float],
    eval_result: dict,
    suggestion_id: str | None = None,
) -> dict[str, Any]:
    """Build one row for the results artifact."""
    row: dict[str, Any] = {
        "evaluation_index": evaluation_index,
        "parameter_values": dict(parameter_values),
        "objective_values": {"surface_response": eval_result["surface_response"]},
        "status": eval_result["status"],
        "failure_reason": eval_result.get("failure_reason"),
        "raw_response": eval_result.get("raw_response"),
        "suggestion_id": suggestion_id,
    }
    return row


def write_results_artifact(rows: list[dict], artifact_dir: str) -> str:
    """Write the results artifact as JSONL and return the path."""
    os.makedirs(artifact_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(artifact_dir, f"results_{timestamp}.jsonl")
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


def print_final_report(rows: list[dict]) -> None:
    """Print the final summary report to stdout with [RESULT] tags."""
    successful = [r for r in rows if r["status"] == "completed"]
    failed = [r for r in rows if r["status"] != "completed"]
    attempted = len(rows)

    best = None
    if successful:
        best = max(successful, key=lambda r: r["objective_values"]["surface_response"])

    print("[RESULT] ====== FINAL REPORT ======")
    print(f"[RESULT] Attempted evaluations : {attempted}")
    print(f"[RESULT] Successful evaluations: {len(successful)}")
    print(f"[RESULT] Failed evaluations     : {len(failed)}")

    if best:
        print(f"[RESULT] Best surface_response : {best['objective_values']['surface_response']:.6f}")
        print(f"[RESULT] Best raw_response     : {best['raw_response']:.6f}")
        print("[RESULT] Best normalized coordinates:")
        for k in sorted(best["parameter_values"]):
            print(f"[RESULT]   {k} = {best['parameter_values'][k]:.6f}")

    print("[RESULT] ====== ALL EVALUATIONS =====")
    print(f"[RESULT] {'idx':>4s}  {'surface_response':>16s}  {'raw_response':>14s}  {'status':>12s}")
    for r in rows:
        sr = r["objective_values"]["surface_response"]
        rr = r.get("raw_response", float("nan"))
        st = r["status"]
        print(f"[RESULT] {r['evaluation_index']:4d}  {sr:16.6f}  {rr:14.6f}  {st:>12s}")

    if failed:
        print("[RESULT] ====== FAILURES =====")
        for r in failed:
            print(f"[RESULT] idx={r['evaluation_index']} reason={r.get('failure_reason', 'unknown')}")