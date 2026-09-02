from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_artifact_dir(artifacts_root: Path, slug: str, campaign_id: str) -> Path:
    artifact_dir = artifacts_root / slug / f"{utc_timestamp()}__{campaign_id[:8]}"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return artifact_dir


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def phase_for_result(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    conditions = metadata.get("conditions") or {}
    phase = conditions.get("phase")
    if phase in {"seed", "warm_start", "bo"}:
        return str(phase)
    return "bo" if row.get("suggestion_id") else "unclassified"


def result_angle(row: dict[str, Any]) -> float | None:
    objective_values = row.get("objective_values") or {}
    value = objective_values.get("static_contact_angle")
    return None if value is None else float(value)


def summarize_results(
    rows: list[dict[str, Any]], *, target: float, tolerance: float
) -> dict[str, Any]:
    counts = {"seed": 0, "warm_start": 0, "bo": 0, "unclassified": 0, "total": len(rows)}
    best_row: dict[str, Any] | None = None
    best_error: float | None = None
    within_tolerance = False

    for row in rows:
        phase = phase_for_result(row)
        counts[phase] = counts.get(phase, 0) + 1
        angle = result_angle(row)
        if angle is None:
            continue
        error = abs(angle - target)
        if best_error is None or error < best_error:
            best_error = error
            best_row = row
        if target - tolerance <= angle <= target + tolerance:
            within_tolerance = True

    best_angle = result_angle(best_row) if best_row else None
    return {
        "counts": counts,
        "best_angle": best_angle,
        "best_abs_error": best_error,
        "within_tolerance": within_tolerance,
    }


def render_summary(summary: dict[str, Any], *, target: float, tolerance: float) -> str:
    counts = summary["counts"]
    if summary["best_angle"] is None:
        best_text = "no submitted measurements"
    else:
        best_text = (
            f"best angle {summary['best_angle']:.3f}° "
            f"(|error|={summary['best_abs_error']:.3f}° vs target {target:.1f}°)"
        )
    return (
        f"seeded={counts.get('seed', 0)}, "
        f"bo results={counts.get('bo', 0)}, total={counts.get('total', 0)}; "
        f"{best_text}; within ±{tolerance:.1f}°={summary['within_tolerance']}"
    )
