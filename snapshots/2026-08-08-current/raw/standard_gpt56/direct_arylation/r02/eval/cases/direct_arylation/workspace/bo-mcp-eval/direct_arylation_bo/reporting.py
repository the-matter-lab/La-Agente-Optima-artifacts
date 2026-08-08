"""Append-only provenance and final campaign reporting."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PARAMETER_NAMES = ("base", "ligand", "solvent", "concentration", "temperature_c")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _result_by_suggestion(results: list[dict]) -> dict[str, dict]:
    return {
        row["suggestion_id"]: row
        for row in results
        if row.get("suggestion_id") is not None
    }


def build_report(
    *, campaign_id: str, suggestions: list[dict], results: list[dict]
) -> dict:
    by_suggestion = _result_by_suggestion(results)
    evaluated = []
    for suggestion in suggestions:
        status = suggestion.get("status")
        if status not in {"completed", "rejected"}:
            continue
        result = by_suggestion.get(suggestion["suggestion_id"], {})
        objective_values = result.get("objective_values") or {}
        evaluated.append(
            {
                "suggestion_id": suggestion["suggestion_id"],
                "status": "successful" if status == "completed" else "failed",
                "parameter_values": result.get("parameter_values")
                or suggestion.get("parameter_values"),
                "yield": objective_values.get("yield"),
                "iteration": suggestion.get("iteration"),
                "created_at": suggestion.get("created_at"),
            }
        )
    evaluated.sort(key=lambda row: (row.get("iteration") or 0, row.get("created_at") or ""))
    successful = [row for row in evaluated if row["status"] == "successful"]
    best = max(successful, key=lambda row: row["yield"], default=None)
    return {
        "campaign_id": campaign_id,
        "generated_at": utc_now(),
        "objective_name": "yield",
        "objective_direction": "maximize",
        "objective_unit": "percent",
        "attempted_evaluations": len(evaluated),
        "successful_evaluations": len(successful),
        "failed_evaluations": len(evaluated) - len(successful),
        "best_measured_yield": None if best is None else best["yield"],
        "best_reaction_conditions": None if best is None else best["parameter_values"],
        "evaluated_candidates": evaluated,
    }


def write_report(artifact_dir: Path, report: dict) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "final_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    columns = ["suggestion_id", "status", *PARAMETER_NAMES, "yield", "iteration"]
    with (artifact_dir / "evaluated_candidates.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in report["evaluated_candidates"]:
            params = row.get("parameter_values") or {}
            writer.writerow(
                {
                    "suggestion_id": row["suggestion_id"],
                    "status": row["status"],
                    **{name: params.get(name) for name in PARAMETER_NAMES},
                    "yield": row.get("yield"),
                    "iteration": row.get("iteration"),
                }
            )
