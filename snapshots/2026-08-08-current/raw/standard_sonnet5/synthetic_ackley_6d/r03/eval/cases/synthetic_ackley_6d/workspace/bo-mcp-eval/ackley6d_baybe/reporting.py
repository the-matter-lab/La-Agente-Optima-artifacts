"""Artifact + summary reporting for the Ackley-6D campaign.

`raw_response` is not persisted server-side (BO-MCP's result schema stores
only `objective_values`), so it is recomputed here directly from the stored
`parameter_values` using the same deterministic objective function used at
evaluation time -- no re-evaluation ambiguity since the function is pure.
"""
import csv
import json
import os

from .objective import OBJECTIVE_NAME, compute_surface_response
from .search_space import PARAMETER_NAMES

FIELDNAMES = [
    "evaluation_index",
    *PARAMETER_NAMES,
    "surface_response",
    "raw_response",
    "status",
    "failure_reason",
    "suggestion_id",
]


def append_failure_record(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def load_failure_records(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_rows(server_results: list[dict], failure_records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for r in server_results:
        pv = r.get("parameter_values", {})
        ov = r.get("objective_values", {})
        raw_response, _ = compute_surface_response(pv)
        rows.append(
            {
                "evaluation_index": 0,
                **{name: pv.get(name) for name in PARAMETER_NAMES},
                "surface_response": ov.get(OBJECTIVE_NAME),
                "raw_response": raw_response,
                "status": "success",
                "failure_reason": "",
                "suggestion_id": r.get("suggestion_id") or "",
            }
        )
    for rec in failure_records:
        pv = rec.get("parameter_values", {})
        rows.append(
            {
                "evaluation_index": 0,
                **{name: pv.get(name) for name in PARAMETER_NAMES},
                "surface_response": None,
                "raw_response": None,
                "status": "failed",
                "failure_reason": rec.get("failure_reason", ""),
                "suggestion_id": rec.get("suggestion_id") or "",
            }
        )
    for i, row in enumerate(rows, start=1):
        row["evaluation_index"] = i
    return rows


def write_results_csv(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize(rows: list[dict]) -> dict:
    successes = [
        r for r in rows if r["status"] == "success" and r["surface_response"] is not None
    ]
    best = max(successes, key=lambda r: r["surface_response"]) if successes else None
    return {"attempted": len(rows), "successful": len(successes), "best": best}
