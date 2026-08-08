"""Rebuild local results.csv/results.jsonl authoritatively from BO-MCP server
state for an existing campaign.

Root-cause context this exists for: local artifacts are only ever written by
`campaign.run`'s loop via `reporting.append_row`. Any result submitted to the
campaign out-of-band (e.g. ad-hoc client calls made while authoring/smoke-
testing this package, before the loop wrote a row for it) is fully present on
the BO-MCP server but silently absent from the local CSV/JSONL. This module
repairs that by treating the server as the single source of truth and
regenerating the local artifact from it — it never mutates campaign lifecycle
(no create/resume/reopen/pause) and is safe to re-run any number of times.

Chronological order (`created_at`) is used to assign `evaluation_index`
1..N, matching how the live loop numbers candidates. Failure detail
(`failure_reason`) has no server-side field, so it is recovered on a
best-effort basis from any pre-existing local JSONL failed rows (matched by
rounded parameter values); a rejected suggestion with no matching prior local
row gets a generic recovered-placeholder reason.
"""

import json
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from . import reporting
from .intake import OBJECTIVE_NAME
from .objective import evaluate
from .search_space import PARAM_NAMES

UNKNOWN_FAILURE_REASON = "unknown (recovered from server; local failure detail unavailable)"


def _load_local_failure_reasons(jsonl_path: Path) -> dict:
    reasons = {}
    if not jsonl_path.exists():
        return reasons
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("status") == "failed":
                key = tuple(round(row["parameter_values"][n], 12) for n in PARAM_NAMES)
                reasons[key] = row.get("failure_reason") or UNKNOWN_FAILURE_REASON
    return reasons


def rebuild_artifacts_from_server(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> list[dict]:
    """Overwrite results.csv/results.jsonl with the authoritative, chronologically
    ordered table derived from BO-MCP. Returns the rebuilt rows."""
    csv_path, jsonl_path = reporting.artifact_paths(artifact_dir)
    prior_failure_reasons = _load_local_failure_reasons(jsonl_path)

    results = client.get_results(campaign_id)
    rejected = client.query_suggestions(campaign_id, status_filter="rejected")

    events = [{"created_at": r["created_at"], "kind": "success", "record": r} for r in results]
    events += [{"created_at": s["created_at"], "kind": "failed", "record": s} for s in rejected]
    events.sort(key=lambda e: e["created_at"])

    rows = []
    for idx, event in enumerate(events, start=1):
        params = event["record"]["parameter_values"]
        if event["kind"] == "success":
            surface = event["record"]["objective_values"][OBJECTIVE_NAME]
            raw = evaluate(params)["raw_response"]
            rows.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": params,
                    "surface_response": surface,
                    "raw_response": raw,
                    "status": "success",
                    "failure_reason": None,
                }
            )
        else:
            key = tuple(round(params[n], 12) for n in PARAM_NAMES)
            rows.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": params,
                    "surface_response": None,
                    "raw_response": None,
                    "status": "failed",
                    "failure_reason": prior_failure_reasons.get(key, UNKNOWN_FAILURE_REASON),
                }
            )

    # Atomic overwrite so a crash mid-rebuild never leaves a truncated artifact.
    tmp_csv, tmp_jsonl = csv_path.with_suffix(".csv.tmp"), jsonl_path.with_suffix(".jsonl.tmp")
    tmp_csv.unlink(missing_ok=True)
    tmp_jsonl.unlink(missing_ok=True)
    for row in rows:
        reporting.append_row(tmp_csv, tmp_jsonl, row, PARAM_NAMES)
    tmp_csv.replace(csv_path)
    tmp_jsonl.replace(jsonl_path)
    return rows
