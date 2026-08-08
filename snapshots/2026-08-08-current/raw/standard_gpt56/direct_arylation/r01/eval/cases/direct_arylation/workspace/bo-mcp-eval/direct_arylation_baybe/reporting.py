import csv
import json
from pathlib import Path

from .intake import MARKER, NONCE, TOTAL_ATTEMPTS


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


def load_attempts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_reports(artifact_dir: Path, campaign: dict, config: dict, bo_results: list[dict]) -> dict:
    attempts = load_attempts(artifact_dir / "attempts.jsonl")
    successes = [row for row in attempts if row["status"] == "success"]
    best = max(successes, key=lambda row: row["objective_value"]) if successes else None
    summary = {
        "schema_version": 1,
        "campaign_id": campaign["id"],
        "campaign_name": campaign["name"],
        "campaign_status": campaign["status"],
        "required_marker": MARKER,
        "cache_buster_nonce": NONCE,
        "backend_requested": config.get("backend_requested"),
        "backend_resolved": config.get("backend_resolved"),
        "objective_name": "yield",
        "objective_direction": "maximize",
        "objective_units": "percent",
        "attempt_budget": TOTAL_ATTEMPTS,
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successes),
        "failed_evaluations": len(attempts) - len(successes),
        "best_reaction_conditions": best["parameter_values"] if best else None,
        "best_measured_yield": best["objective_value"] if best else None,
        "all_evaluated_candidates": attempts,
    }
    (artifact_dir / "progress_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "bo_results.json").write_text(
        json.dumps(bo_results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if len(attempts) == TOTAL_ATTEMPTS:
        (artifact_dir / "final_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    fields = [
        "attempt_number", "suggestion_id", "status", "objective_name", "objective_value",
        "objective_units", "base", "ligand", "solvent", "concentration", "temperature_c",
        "http_status", "error", "attempted_at_utc",
    ]
    with (artifact_dir / "evaluated_candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in attempts:
            flat = {key: row.get(key) for key in fields}
            flat.update(row["parameter_values"])
            writer.writerow(flat)
    return summary
