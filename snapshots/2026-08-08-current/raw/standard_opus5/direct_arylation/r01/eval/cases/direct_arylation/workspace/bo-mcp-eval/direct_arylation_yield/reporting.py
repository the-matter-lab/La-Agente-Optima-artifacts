"""Attempt records, local JSON artifacts, tagged stdout and the final report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def say(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_record(
    *,
    attempt: int,
    campaign_id: str,
    nonce: str,
    suggestion_id: str | None,
    parameter_values: dict,
    objective_name: str,
    status: str,
    objective_value: float | None,
    detail: str,
) -> dict:
    """One record per attempted evaluation, with standardized value objects."""
    record = {
        "attempt": attempt,
        "attempted_at": now(),
        "campaign_id": campaign_id,
        "nonce": nonce,
        "suggestion_id": suggestion_id,
        "status": status,
        "parameter_values": parameter_values,
        "objective_values": {objective_name: objective_value} if objective_value is not None else None,
        "detail": detail,
    }
    return record


class Artifacts:
    """Append-only provenance for one campaign; never read back for loop decisions."""

    def __init__(self, root: Path, campaign_id: str) -> None:
        self.dir = Path(root) / campaign_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.attempts_jsonl = self.dir / "attempts.jsonl"
        self.attempts_json = self.dir / "attempts.json"
        self.report_json = self.dir / "final_report.json"
        # Prior invocations' attempts, mirrored into attempts.json for provenance only.
        self._prior: list[dict] = [
            json.loads(line)
            for line in self.attempts_jsonl.read_text().splitlines()
            if line.strip()
        ] if self.attempts_jsonl.exists() else []
        self._records: list[dict] = []

    def add(self, record: dict) -> None:
        self._records.append(record)
        with self.attempts_jsonl.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        self.attempts_json.write_text(json.dumps(self._prior + self._records, indent=2))

    @property
    def records(self) -> list[dict]:
        """Attempts made during this invocation."""
        return list(self._records)

    @property
    def all_records(self) -> list[dict]:
        """Every attempt recorded for this campaign, across invocations."""
        return self._prior + self._records


def format_conditions(parameter_values: dict) -> str:
    return " | ".join(f"{k}={v}" for k, v in parameter_values.items())


def announce_result(record: dict, *, objective_name: str, unit: str, budget: int, best: float | None) -> None:
    values = record["objective_values"]
    measured = f"{values[objective_name]:.2f} {unit}" if values else "n/a"
    best_txt = f"{best:.2f} {unit}" if best is not None else "n/a"
    say(
        "RESULT",
        f"attempt {record['attempt']}/{budget} status={record['status']} "
        f"{objective_name}={measured} best_so_far={best_txt}\n"
        f"          conditions: {format_conditions(record['parameter_values'])}",
    )
    if record["status"] != "success":
        say("ALERT", f"attempt {record['attempt']} failed: {record['detail']}")


def build_report(
    *,
    campaign_id: str,
    campaign_name: str,
    nonce: str,
    objective_name: str,
    unit: str,
    server_results: list[dict],
    records: list[dict],
    all_records: list[dict],
    budget: int,
) -> dict:
    """Merge server-side successes with this invocation's failed attempts."""
    successes = [
        {
            "status": "success",
            "parameter_values": row.get("parameter_values", {}),
            "objective_values": {objective_name: row.get("objective_values", {}).get(objective_name)},
        }
        for row in server_results
    ]
    failures = [
        {
            "status": "failed",
            "parameter_values": rec["parameter_values"],
            "objective_values": None,
            "detail": rec["detail"],
        }
        for rec in all_records
        if rec["status"] != "success"
    ]
    scored = [c for c in successes if isinstance(c["objective_values"].get(objective_name), (int, float))]
    best = max(scored, key=lambda c: c["objective_values"][objective_name], default=None)
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "nonce": nonce,
        "objective_name": objective_name,
        "objective_direction": "maximize",
        "objective_units": unit,
        "invocation_budget": budget,
        "n_attempted_evaluations_this_invocation": len(records),
        "n_successful_evaluations_this_invocation": sum(1 for r in records if r["status"] == "success"),
        "n_failed_evaluations_this_invocation": sum(1 for r in records if r["status"] != "success"),
        "n_attempted_evaluations_campaign": len(all_records),
        "n_successful_evaluations_campaign": len(successes),
        "best_reaction_conditions": best["parameter_values"] if best else None,
        "best_measured_yield": best["objective_values"][objective_name] if best else None,
        "evaluated_candidates": successes + failures,
    }


def announce_report(report: dict, artifacts: Artifacts) -> None:
    artifacts.report_json.write_text(json.dumps(report, indent=2))
    unit = report["objective_units"]
    best = report["best_measured_yield"]
    say("EVENT", f"campaign {report['campaign_id']} — final report")
    say(
        "RESULT",
        f"best {report['objective_name']} = "
        + (f"{best:.2f} {unit}" if best is not None else "n/a")
        + "\n          best conditions: "
        + (format_conditions(report["best_reaction_conditions"]) if best is not None else "n/a")
        + f"\n          attempted this invocation: {report['n_attempted_evaluations_this_invocation']}"
        f" | successful: {report['n_successful_evaluations_this_invocation']}"
        f" | failed: {report['n_failed_evaluations_this_invocation']}"
        f"\n          campaign totals: attempted={report['n_attempted_evaluations_campaign']}"
        f" successful={report['n_successful_evaluations_campaign']}"
        f"\n          artifacts: {artifacts.dir}",
    )
