"""Objective extraction, artifacts and UI-friendly reporting."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .objective import OBJECTIVE_NAME, evaluate
from .space import PARAM_NAMES

RESULTS_JSONL = "results.jsonl"
RESULTS_CSV = "results_table.csv"
FINAL_JSON = "final_report.json"
RUN_LOG = "run.log"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_artifact_dir(base: str) -> Path:
    path = Path(base) / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_row(index: int, campaign_id: str, evaluated: dict, submitted: bool) -> dict:
    """Artifact row for one attempted evaluation (append-only provenance)."""
    values = evaluated.get("values") or {}
    return {
        "evaluation_index": index,
        "timestamp": now(),
        "campaign_id": campaign_id,
        "suggestion_id": evaluated.get("suggestion_id"),
        "parameter_values": {k: evaluated["parameter_values"][k] for k in PARAM_NAMES},
        "objective_values": (
            {OBJECTIVE_NAME: values[OBJECTIVE_NAME]} if evaluated["status"] == "success" else {}
        ),
        "raw_response": values.get("raw_response"),
        "status": evaluated["status"],
        "failure_reason": evaluated.get("failure_reason"),
        "submitted_to_bo_mcp": submitted,
    }


def append_row(artifact_dir: Path, row: dict) -> None:
    with (artifact_dir / RESULTS_JSONL).open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def campaign_rows(server_results: list[dict], artifact_base: str) -> list[dict]:
    """Full campaign table: server-persisted successes plus every recorded failure.

    Reporting only — the optimization loop never reads artifacts back.
    """
    rows = []
    for res in server_results:
        rows.append(
            {
                "timestamp": res.get("created_at"),
                "campaign_id": res.get("campaign_id"),
                "suggestion_id": res.get("suggestion_id"),
                "parameter_values": {k: res["parameter_values"][k] for k in PARAM_NAMES},
                "objective_values": {OBJECTIVE_NAME: res["objective_values"][OBJECTIVE_NAME]},
                "raw_response": evaluate(res["parameter_values"])["raw_response"],
                "status": "success",
                "failure_reason": None,
                "submitted_to_bo_mcp": True,
            }
        )
    for path in sorted(Path(artifact_base).glob("*/" + RESULTS_JSONL)):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("status") != "success":
                rows.append(row)
    rows.sort(key=lambda r: r.get("timestamp") or "")
    for i, row in enumerate(rows, start=1):
        row["evaluation_index"] = i
    return rows



def best_of(rows: list[dict]) -> dict | None:
    ok = [r for r in rows if r["status"] == "success"]
    return max(ok, key=lambda r: r["objective_values"][OBJECTIVE_NAME]) if ok else None


def fmt_point(row: dict) -> str:
    return " ".join(f"{row['parameter_values'][k]:.4f}" for k in PARAM_NAMES)


def result_line(row: dict, best: dict | None) -> str:
    if row["status"] != "success":
        return (
            f"[RESULT] #{row['evaluation_index']:02d} FAILED x=[{fmt_point(row)}] "
            f"reason={row['failure_reason']}"
        )
    best_txt = f"{best['objective_values'][OBJECTIVE_NAME]:.6f}" if best else "n/a"
    return (
        f"[RESULT] #{row['evaluation_index']:02d} ok  x=[{fmt_point(row)}]  "
        f"{OBJECTIVE_NAME}={row['objective_values'][OBJECTIVE_NAME]:.6f}  "
        f"raw={row['raw_response']:.6f}  best_so_far={best_txt}"
    )


def write_table(artifact_dir: Path, rows: list[dict]) -> Path:
    path = artifact_dir / RESULTS_CSV
    fields = ["evaluation_index", *PARAM_NAMES, OBJECTIVE_NAME, "raw_response", "status", "failure_reason"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "evaluation_index": row["evaluation_index"],
                    **{k: row["parameter_values"][k] for k in PARAM_NAMES},
                    OBJECTIVE_NAME: row["objective_values"].get(OBJECTIVE_NAME, ""),
                    "raw_response": row["raw_response"],
                    "status": row["status"],
                    "failure_reason": row["failure_reason"] or "",
                }
            )
    return path


def write_final(
    artifact_dir: Path,
    campaign_id: str,
    rows: list[dict],
    diagnostics: dict | None,
    invocation_attempted: int = 0,
) -> dict:
    best = best_of(rows)
    summary = {
        "campaign_id": campaign_id,
        "campaign_marker": "akg-eval-2a04c50f6e2f4a42952ebc5cbc96b431",
        "nonce": "c02de9f3-c0fa-4590-bebf-d77d7aa55ad1",
        "objective_name": OBJECTIVE_NAME,
        "attempted_evaluations": len(rows),
        "successful_evaluations": sum(1 for r in rows if r["status"] == "success"),
        "failed_evaluations": sum(1 for r in rows if r["status"] != "success"),
        "attempted_this_invocation": invocation_attempted,
        "best_parameters": best["parameter_values"] if best else None,
        "best_surface_response": best["objective_values"][OBJECTIVE_NAME] if best else None,
        "best_raw_response": best["raw_response"] if best else None,
        "evaluations": rows,
        "diagnostics": diagnostics,
        "generated_at": now(),
    }
    (artifact_dir / FINAL_JSON).write_text(json.dumps(summary, indent=2))
    return summary


def print_summary(summary: dict, artifact_dir: Path) -> None:
    print(f"[EVENT] campaign_id={summary['campaign_id']}")
    print(
        f"[EVENT] evaluations attempted={summary['attempted_evaluations']} "
        f"successful={summary['successful_evaluations']} failed={summary['failed_evaluations']}"
    )
    if summary["best_surface_response"] is not None:
        point = " ".join(f"{summary['best_parameters'][k]:.6f}" for k in PARAM_NAMES)
        print(f"[RESULT] BEST {OBJECTIVE_NAME}={summary['best_surface_response']:.6f}")
        print(f"[RESULT] BEST raw_response={summary['best_raw_response']:.6f}")
        print(f"[RESULT] BEST x=[{point}]")
    else:
        print("[ALERT] no successful evaluation recorded")
    print(f"[EVENT] artifacts={artifact_dir}/ ({RESULTS_JSONL}, {RESULTS_CSV}, {FINAL_JSON}, {RUN_LOG})")
