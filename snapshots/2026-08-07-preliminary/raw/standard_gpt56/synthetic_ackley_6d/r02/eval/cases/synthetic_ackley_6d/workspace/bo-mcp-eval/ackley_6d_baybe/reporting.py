import csv
import json
from pathlib import Path

from .search_space import PARAMETER_NAMES


def append_evaluation(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def load_evaluations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_reports(artifact_dir: Path, campaign_id: str) -> dict:
    rows = load_evaluations(artifact_dir / "evaluations.jsonl")
    successes = [row for row in rows if row["status"] == "success"]
    best = max(successes, key=lambda row: row["objective_values"]["surface_response"], default=None)
    summary = {
        "campaign_id": campaign_id,
        "objective_name": "surface_response",
        "objective_direction": "maximize",
        "objective_unit": "normalized_unitless",
        "attempted_evaluations": len(rows),
        "successful_evaluations": len(successes),
        "best_normalized_coordinates": best["parameter_values"] if best else None,
        "best_raw_response": best.get("raw_response") if best else None,
        "best_surface_response": (
            best["objective_values"]["surface_response"] if best else None
        ),
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    fields = ["evaluation_index", *PARAMETER_NAMES, "surface_response", "raw_response", "status", "failure_reason"]
    with (artifact_dir / "evaluations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "evaluation_index": row["evaluation_index"],
                    **row["parameter_values"],
                    "surface_response": row.get("objective_values", {}).get("surface_response"),
                    "raw_response": row.get("raw_response"),
                    "status": row["status"],
                    "failure_reason": row.get("failure_reason"),
                }
            )

    table = [
        "| index | x_1 | x_2 | x_3 | x_4 | x_5 | x_6 | surface_response | raw_response | status | failure_reason |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        values = row["parameter_values"]
        table.append(
            "| {idx} | {xs} | {surface} | {raw} | {status} | {reason} |".format(
                idx=row["evaluation_index"],
                xs=" | ".join(f"{values[name]:.12g}" for name in PARAMETER_NAMES),
                surface=(
                    f"{row.get('objective_values', {}).get('surface_response'):.12g}"
                    if row.get("objective_values", {}).get("surface_response") is not None
                    else ""
                ),
                raw=f"{row['raw_response']:.12g}" if row.get("raw_response") is not None else "",
                status=row["status"],
                reason=row.get("failure_reason") or "",
            )
        )
    report = ["# Ackley 6D BayBE Campaign Results", "", "```json", json.dumps(summary, indent=2, sort_keys=True), "```", "", *table, ""]
    (artifact_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    return summary
