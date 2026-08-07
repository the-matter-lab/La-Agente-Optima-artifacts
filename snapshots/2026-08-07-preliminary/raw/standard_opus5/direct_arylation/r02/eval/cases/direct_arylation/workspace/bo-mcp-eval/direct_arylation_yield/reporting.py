"""Objective extraction, artifact provenance, and end-of-invocation reporting."""

import json
from pathlib import Path


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def log(path: Path, message: str) -> None:
    with path.open("a") as handle:
        handle.write(message + "\n")


def result_rows(results: list[dict], objective_name: str) -> list[dict]:
    """Flatten server result rows to {parameters, value} records."""
    rows = []
    for row in results:
        params = row.get("parameter_values") or {}
        value = (row.get("objective_values") or {}).get(objective_name)
        if value is None:
            continue
        rows.append({"parameters": params, "value": float(value)})
    return rows


def failed_rows(suggestions: list[dict]) -> list[dict]:
    return [{"parameters": s.get("parameter_values") or {}} for s in suggestions]


def fmt_candidate(params: dict) -> str:
    order = ["base", "ligand", "solvent", "concentration", "temperature_c"]
    keys = [k for k in order if k in params] + [k for k in params if k not in order]
    return " | ".join(f"{k}={params[k]}" for k in keys)


def build_report(rows: list[dict], failures: list[dict], objective_name: str) -> dict:
    best = max(rows, key=lambda r: r["value"]) if rows else None
    return {
        "objective_name": objective_name,
        "objective_direction": "maximize",
        "unit": "percent",
        "attempted_evaluations": len(rows) + len(failures),
        "successful_evaluations": len(rows),
        "failed_evaluations": len(failures),
        "best_conditions": best["parameters"] if best else None,
        "best_measured_yield_percent": best["value"] if best else None,
        "evaluated_candidates": [
            {"status": "success", "parameters": r["parameters"], objective_name: r["value"]}
            for r in rows
        ]
        + [
            {"status": "failed", "parameters": f["parameters"], objective_name: None}
            for f in failures
        ],
    }


def write_report(directory: Path, report: dict) -> Path:
    path = directory / "report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def print_report(report: dict, emit) -> None:
    name = report["objective_name"]
    emit("EVENT", "=== CAMPAIGN SUMMARY ===")
    emit(
        "RESULT",
        f"attempted={report['attempted_evaluations']} "
        f"successful={report['successful_evaluations']} "
        f"failed={report['failed_evaluations']}",
    )
    if report["best_measured_yield_percent"] is None:
        emit("ALERT", "no successful evaluation recorded yet")
    else:
        emit(
            "RESULT",
            f"best {name} = {report['best_measured_yield_percent']:.2f} percent "
            f"@ {fmt_candidate(report['best_conditions'])}",
        )
    for i, cand in enumerate(report["evaluated_candidates"], start=1):
        value = cand[name]
        shown = f"{value:.2f}" if isinstance(value, float) else "n/a"
        emit(
            "RESULT",
            f"#{i:02d} [{cand['status']}] {name}={shown} :: {fmt_candidate(cand['parameters'])}",
        )
