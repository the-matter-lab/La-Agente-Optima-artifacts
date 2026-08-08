from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .search_space import (
    CACHE_BUSTER_NONCE,
    OBJECTIVE_NAME,
    PARAMETER_NAMES,
)

RESULTS_JSONL = "evaluations.jsonl"
RESULTS_CSV = "evaluated_candidates.csv"
SUMMARY_JSON = "summary.json"
REPORT_MD = "report.md"
RUN_LOG = "run.log"
CAMPAIGN_ID_FILE = "campaign_id.txt"


def ensure_artifact_dir(artifact_root: str | Path, campaign_id: str) -> Path:
    path = Path(artifact_root) / campaign_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _surface_value(record: dict[str, Any]) -> float | None:
    objective_values = record.get("objective_values") or {}
    value = objective_values.get(OBJECTIVE_NAME)
    return None if value is None else float(value)


def summarize_records(records: list[dict[str, Any]], campaign_id: str, artifact_dir: Path) -> dict[str, Any]:
    successful = [record for record in records if record.get("status") == "completed"]
    attempted = len(records)
    summary: dict[str, Any] = {
        "campaign_id": campaign_id,
        "artifact_dir": str(artifact_dir),
        "results_jsonl": str(artifact_dir / RESULTS_JSONL),
        "results_csv": str(artifact_dir / RESULTS_CSV),
        "report_md": str(artifact_dir / REPORT_MD),
        "successful_evaluations": len(successful),
        "attempted_evaluations": attempted,
        "cache_buster_nonce": CACHE_BUSTER_NONCE,
    }
    if successful:
        best = max(successful, key=lambda record: _surface_value(record) or float("-inf"))
        summary["best_normalized_coordinates"] = best["parameter_values"]
        summary["best_raw_response"] = best.get("raw_response")
        summary["best_surface_response"] = _surface_value(best)
    else:
        summary["best_normalized_coordinates"] = None
        summary["best_raw_response"] = None
        summary["best_surface_response"] = None
    return summary


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "evaluation_index",
        *PARAMETER_NAMES,
        OBJECTIVE_NAME,
        "status",
        "failure_reason",
        "raw_response",
        "suggestion_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "evaluation_index": record.get("evaluation_index"),
                OBJECTIVE_NAME: _surface_value(record),
                "status": record.get("status"),
                "failure_reason": record.get("failure_reason"),
                "raw_response": record.get("raw_response"),
                "suggestion_id": record.get("suggestion_id"),
            }
            parameter_values = record.get("parameter_values") or {}
            for name in PARAMETER_NAMES:
                row[name] = parameter_values.get(name)
            writer.writerow(row)


def _format_float(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.12f}"


def write_report(path: Path, summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lines = [
        "# Ackley 6D BO-MCP benchmark report",
        "",
        f"- Campaign ID: `{summary['campaign_id']}`",
        f"- Cache-buster nonce: `{CACHE_BUSTER_NONCE}`",
        f"- Attempted evaluations: {summary['attempted_evaluations']}",
        f"- Successful evaluations: {summary['successful_evaluations']}",
        f"- Best normalized coordinates: `{json.dumps(summary['best_normalized_coordinates'], sort_keys=True)}`",
        f"- Best raw_response: `{summary['best_raw_response']}`",
        f"- Best {OBJECTIVE_NAME}: `{summary['best_surface_response']}`",
        "",
        "## Evaluated candidates",
        "",
        "| evaluation_index | x_1 | x_2 | x_3 | x_4 | x_5 | x_6 | surface_response | raw_response | status | failure_reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        parameter_values = record.get("parameter_values") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(record.get("evaluation_index", "")),
                    *[_format_float(parameter_values.get(name)) for name in PARAMETER_NAMES],
                    _format_float(_surface_value(record)),
                    _format_float(record.get("raw_response")),
                    str(record.get("status", "")),
                    str(record.get("failure_reason", "") or ""),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_campaign_id_file(path: Path, campaign_id: str) -> None:
    path.write_text(f"BO_MCP_CAMPAIGN_ID={campaign_id}\n", encoding="utf-8")


def write_summary_files(artifact_dir: Path, campaign_id: str) -> dict[str, Any]:
    records = load_jsonl(artifact_dir / RESULTS_JSONL)
    summary = summarize_records(records, campaign_id, artifact_dir)
    write_csv(artifact_dir / RESULTS_CSV, records)
    write_report(artifact_dir / REPORT_MD, summary, records)
    (artifact_dir / SUMMARY_JSON).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_campaign_id_file(artifact_dir / CAMPAIGN_ID_FILE, campaign_id)
    return summary
