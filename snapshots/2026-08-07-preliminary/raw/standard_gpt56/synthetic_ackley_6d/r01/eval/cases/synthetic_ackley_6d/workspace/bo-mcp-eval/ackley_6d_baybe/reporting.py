import csv
import json
from pathlib import Path


def append_evaluation(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_reports(jsonl_path: Path, artifact_dir: Path, campaign_id: str) -> dict:
    rows = []
    if jsonl_path.exists():
        rows = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    rows.sort(key=lambda row: row["evaluation_index"])
    csv_path = artifact_dir / "evaluations.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["evaluation_index", "parameter_values", "objective_values", "status", "failure_reason", "raw_response"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "parameter_values": json.dumps(row["parameter_values"], sort_keys=True), "objective_values": json.dumps(row["objective_values"], sort_keys=True)})
    successful = [row for row in rows if row["status"] == "success"]
    best = max(successful, key=lambda row: row["objective_values"]["surface_response"], default=None)
    summary = {
        "campaign_id": campaign_id,
        "attempted_evaluations": len(rows),
        "successful_evaluations": len(successful),
        "best": best,
        "evaluations_jsonl": str(jsonl_path),
        "evaluations_csv": str(csv_path),
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
