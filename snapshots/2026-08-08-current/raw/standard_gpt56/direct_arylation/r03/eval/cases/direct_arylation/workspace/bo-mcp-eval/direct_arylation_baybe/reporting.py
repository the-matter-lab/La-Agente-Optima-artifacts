import json
from pathlib import Path

from .search_space import normalize_candidate

PARAMETER_NAMES = ["base", "ligand", "solvent", "concentration", "temperature_c"]


def append_attempt(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def collect_attempts(client, campaign_id: str) -> list[dict]:
    suggestions = client.query_suggestions(campaign_id, limit=500)
    results = client.get_results(campaign_id)
    by_suggestion = {row.get("suggestion_id"): row for row in results if row.get("suggestion_id")}
    attempts = []
    for suggestion in suggestions:
        status = suggestion.get("status")
        if status not in {"completed", "rejected"}:
            continue
        result = by_suggestion.get(suggestion["suggestion_id"])
        raw_values = suggestion.get("parameter_values") or (result or {}).get("parameter_values", {})
        values = normalize_candidate(raw_values)
        value = (result or {}).get("objective_values", {}).get("yield")
        attempts.append(
            {
                "suggestion_id": suggestion["suggestion_id"],
                "status": "success" if result is not None else "failed",
                "parameters": [{"name": name, "value": values.get(name)} for name in PARAMETER_NAMES],
                "objectives": [{"name": "yield", "value": value, "unit": "percent"}],
                "error": None if result is not None else "oracle evaluation failed",
                "created_at": suggestion.get("created_at"),
            }
        )
    return sorted(attempts, key=lambda row: (row["created_at"] or "", row["suggestion_id"]))


def write_final_report(path: Path, campaign_id: str, attempts: list[dict]) -> dict:
    successes = [row for row in attempts if row["status"] == "success"]
    best = max(successes, key=lambda row: row["objectives"][0]["value"], default=None)
    report = {
        "campaign_id": campaign_id,
        "objective": {"name": "yield", "direction": "maximize", "unit": "percent"},
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successes),
        "best_reaction_conditions": best["parameters"] if best else None,
        "best_measured_yield": best["objectives"][0]["value"] if best else None,
        "attempts": attempts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
