from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .search_space import MARKER, OBJECTIVE_NAME


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    attempts: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                attempts.append(json.loads(line))
    return attempts


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def candidate_text(candidate: dict[str, Any]) -> str:
    return (
        f"base={candidate['base']} | ligand={candidate['ligand']} | solvent={candidate['solvent']} | "
        f"concentration={candidate['concentration']} | temperature_c={candidate['temperature_c']}"
    )


def summarise_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [a for a in attempts if a.get("status") == "success"]
    failures = [a for a in attempts if a.get("status") != "success"]
    best = max(successes, key=lambda item: item[OBJECTIVE_NAME], default=None)
    return {
        "marker": MARKER,
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successes),
        "failed_evaluations": len(failures),
        "best": best,
        "attempts": attempts,
    }


def write_reports(*, artifact_dir: Path, campaign_id: str, attempts: list[dict[str, Any]], diagnostics: dict[str, Any] | None) -> dict[str, str]:
    summary = summarise_attempts(attempts)
    summary["campaign_id"] = campaign_id
    summary_path = artifact_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    diagnostics_path = artifact_dir / "diagnostics.json"
    if diagnostics is not None:
        with diagnostics_path.open("w", encoding="utf-8") as handle:
            json.dump(diagnostics, handle, indent=2, sort_keys=True)

    markdown_path = artifact_dir / "report.md"
    best = summary["best"]
    lines = [
        f"# Direct Arylation BO Report ({MARKER})",
        "",
        f"- Campaign ID: `{campaign_id}`",
        f"- Attempted evaluations: {summary['attempted_evaluations']}",
        f"- Successful evaluations: {summary['successful_evaluations']}",
        f"- Failed evaluations: {summary['failed_evaluations']}",
    ]
    if best is None:
        lines.extend(["- Best measured yield: n/a", "- Best reaction conditions: n/a"])
    else:
        lines.extend(
            [
                f"- Best measured yield: {best[OBJECTIVE_NAME]:.4f}",
                f"- Best reaction conditions: {candidate_text(best['candidate'])}",
            ]
        )
    lines.extend(["", "## Evaluated candidates", ""])
    lines.append("| # | Status | Yield | Conditions |")
    lines.append("| - | ------ | ----- | ---------- |")
    for attempt in attempts:
        value = "" if attempt.get(OBJECTIVE_NAME) is None else f"{attempt[OBJECTIVE_NAME]:.4f}"
        lines.append(
            f"| {attempt['attempt_index']} | {attempt['status']} | {value} | {candidate_text(attempt['candidate'])} |"
        )
    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    return {
        "summary_json": str(summary_path),
        "report_md": str(markdown_path),
        "diagnostics_json": str(diagnostics_path) if diagnostics is not None else "",
    }
