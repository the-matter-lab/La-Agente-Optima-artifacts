"""Append-only provenance + final report building for the campaign run."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .search_space import OBJECTIVE_NAME


def artifacts_dir(campaign_id: str) -> Path:
    d = Path("artifacts") / "direct_arylation_bo" / campaign_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_attempt_jsonl(campaign_id: str, entry: dict[str, Any]) -> None:
    path = artifacts_dir(campaign_id) / "attempts.jsonl"
    entry = {"ts": time.time(), **entry}
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def build_final_report(
    *,
    client,
    campaign_id: str,
) -> dict[str, Any]:
    """Re-derive the full campaign evaluation history from the server.

    This is authoritative (covers every invocation of this campaign, not
    just the current process), unlike the local attempts.jsonl provenance.
    """
    results = client.get_results(campaign_id)
    rejected = client.query_suggestions(campaign_id, status_filter="rejected", limit=500)

    candidates: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for r in results:
        y = r.get("objective_values", {}).get(OBJECTIVE_NAME)
        entry = {
            "status": "success",
            "parameter_values": r.get("parameter_values"),
            "yield": y,
            "suggestion_id": r.get("suggestion_id"),
            "result_id": r.get("id"),
        }
        candidates.append(entry)
        if y is not None and (best is None or y > best["yield"]):
            best = entry

    for s in rejected:
        candidates.append(
            {
                "status": "failed",
                "parameter_values": s.get("parameter_values"),
                "yield": None,
                "suggestion_id": s.get("suggestion_id"),
                "result_id": None,
            }
        )

    n_success = len(results)
    n_failed = len(rejected)
    report = {
        "campaign_id": campaign_id,
        "objective_name": OBJECTIVE_NAME,
        "objective_direction": "maximize",
        "attempted_evaluations": n_success + n_failed,
        "successful_evaluations": n_success,
        "failed_evaluations": n_failed,
        "best_conditions": best.get("parameter_values") if best else None,
        "best_measured_yield": best.get("yield") if best else None,
        "all_evaluated_candidates": candidates,
    }
    path = artifacts_dir(campaign_id) / "final_report.json"
    path.write_text(json.dumps(report, indent=2))
    return report
