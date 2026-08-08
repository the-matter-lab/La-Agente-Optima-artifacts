"""Artifacts (append-only JSONL) and concise tagged stdout reporting."""

import json
from pathlib import Path

from .objective import OBJECTIVE_NAME, OBJECTIVE_UNIT
from .space import PARAM_NAMES


def _record(row: dict) -> dict:
    values = row.get("values") or {}
    return {
        "evaluation_index": row["evaluation_index"],
        "suggestion_id": row.get("suggestion_id"),
        "parameter_values": {k: row["parameter_values"][k] for k in PARAM_NAMES},
        "objective_values": (
            {OBJECTIVE_NAME: values[OBJECTIVE_NAME]} if values else {}
        ),
        "raw_response": values.get("raw_response"),
        "status": row["status"],
        "failure_reason": row.get("failure_reason"),
    }


def append_rows(path: Path, rows: list[dict]) -> None:
    with path.open("a") as fh:
        for row in rows:
            fh.write(json.dumps(_record(row)) + "\n")


def print_result(row: dict, out) -> None:
    rec = _record(row)
    coords = " ".join(f"{k}={rec['parameter_values'][k]:.4f}" for k in PARAM_NAMES)
    if rec["status"] == "success":
        out(
            f"[RESULT] eval #{rec['evaluation_index']:02d} | {coords} | "
            f"raw_response={rec['raw_response']:.6f} | "
            f"{OBJECTIVE_NAME}={rec['objective_values'][OBJECTIVE_NAME]:.6f} "
            f"[{OBJECTIVE_UNIT}] | status=success"
        )
    else:
        out(
            f"[RESULT] eval #{rec['evaluation_index']:02d} | {coords} | "
            f"status=failed | reason={rec['failure_reason']}"
        )


def final_report(campaign_id: str, rows: list[dict], attempted: int, out) -> None:
    records = [_record(r) for r in rows]
    ok = [r for r in records if r["status"] == "success"]
    out("[EVENT] campaign summary")
    out(f"  campaign_id            : {campaign_id}")
    out(f"  attempted evaluations  : {attempted}")
    out(f"  successful evaluations : {len(ok)}")
    out(f"  failed evaluations     : {attempted - len(ok)}")
    if ok:
        best = max(ok, key=lambda r: r["objective_values"][OBJECTIVE_NAME])
        coords = ", ".join(
            f"{k}={best['parameter_values'][k]:.6f}" for k in PARAM_NAMES
        )
        out(f"  best coordinates       : {coords}")
        out(f"  best raw_response      : {best['raw_response']:.6f}")
        out(
            f"  best {OBJECTIVE_NAME}  : "
            f"{best['objective_values'][OBJECTIVE_NAME]:.6f} [{OBJECTIVE_UNIT}]"
        )
    out("[EVENT] evaluated candidates")
    header = "  idx | " + " | ".join(f"{k:>8}" for k in PARAM_NAMES)
    out(header + " |     raw_response |  surface_response | status")
    for r in records:
        coords = " | ".join(f"{r['parameter_values'][k]:8.4f}" for k in PARAM_NAMES)
        if r["status"] == "success":
            out(
                f"  {r['evaluation_index']:3d} | {coords} | "
                f"{r['raw_response']:16.6f} | "
                f"{r['objective_values'][OBJECTIVE_NAME]:17.6f} | success"
            )
        else:
            out(
                f"  {r['evaluation_index']:3d} | {coords} | "
                f"{'n/a':>16} | {'n/a':>17} | failed ({r['failure_reason']})"
            )
