"""Tagged stdout, run log, and append-only attempt/report artifacts."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path("artifacts")
LOG_DIR = Path("logs")


class Reporter:
    """Concise tagged stdout plus a verbose on-disk run log."""

    def __init__(self, stamp: str) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        ARTIFACT_DIR.mkdir(exist_ok=True)
        self.log_path = LOG_DIR / f"run_{stamp}.log"
        self.attempts_path = ARTIFACT_DIR / "attempts.jsonl"
        self.report_path = ARTIFACT_DIR / f"final_report_{stamp}.json"
        self.snapshot_path = ARTIFACT_DIR / "attempts.json"

    def log(self, message: str) -> None:
        with self.log_path.open("a") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {message}\n")

    def tag(self, tag: str, message: str) -> None:
        print(f"[{tag}] {message}", flush=True)
        self.log(f"[{tag}] {message}")

    def event(self, message: str) -> None:
        self.tag("EVENT", message)

    def alert(self, message: str) -> None:
        self.tag("ALERT", message)

    def heartbeat(self, message: str) -> None:
        self.tag("HEARTBEAT", message)

    def result(self, record: dict[str, Any]) -> None:
        params = record["parameter_values"]
        conditions = (
            f"base={params['base']} | ligand={params['ligand']} | solvent={params['solvent']} "
            f"| conc={params['concentration']} M | T={params['temperature_c']} C"
        )
        if record["status"] == "success":
            value = record["objective_values"]["yield"]
            self.tag(
                "RESULT",
                f"attempt {record['attempt']}/{record['attempt_budget']} this run "
                f"(success {record['successes']}) yield={value:.2f}% "
                f"best={record['best_yield']:.2f}% | {conditions}",
            )
        else:
            self.tag(
                "RESULT",
                f"attempt {record['attempt']}/{record['attempt_budget']} this run FAILED "
                f"({record.get('error', 'unknown error')}) | {conditions}",
            )

    def record_attempt(self, record: dict[str, Any]) -> None:
        with self.attempts_path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def load_attempts(self) -> list[dict[str, Any]]:
        """All attempts recorded for this workspace (reporting only, never loop state)."""
        if not self.attempts_path.exists():
            return []
        return [json.loads(line) for line in self.attempts_path.read_text().splitlines() if line]

    def write_snapshot(self, attempts: list[dict[str, Any]]) -> None:
        self.snapshot_path.write_text(json.dumps(attempts, indent=2))


    def write_report(self, report: dict[str, Any]) -> None:
        self.report_path.write_text(json.dumps(report, indent=2))


def summarize(campaign_id: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [a for a in attempts if a["status"] == "success"]
    best = max(successes, key=lambda a: a["objective_values"]["yield"], default=None)
    return {
        "campaign_id": campaign_id,
        "objective": {"name": "yield", "direction": "maximize", "unit": "percent"},
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successes),
        "failed_evaluations": len(attempts) - len(successes),
        "best_yield_percent": best["objective_values"]["yield"] if best else None,
        "best_conditions": best["parameter_values"] if best else None,
        "evaluated_candidates": attempts,
    }


def print_summary(reporter: Reporter, report: dict[str, Any]) -> None:
    reporter.event(
        f"summary: attempted={report['attempted_evaluations']} "
        f"successful={report['successful_evaluations']} "
        f"failed={report['failed_evaluations']}"
    )
    if report["best_conditions"]:
        best = report["best_conditions"]
        reporter.event(
            f"best yield={report['best_yield_percent']:.2f}% at base={best['base']} | "
            f"ligand={best['ligand']} | solvent={best['solvent']} | "
            f"conc={best['concentration']} M | T={best['temperature_c']} C"
        )
    reporter.event(f"artifacts: {reporter.snapshot_path} | {reporter.report_path}")
    reporter.event(f"run log: {reporter.log_path}")
    sys.stdout.flush()
