from __future__ import annotations

import csv
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import logfire

sys.path.insert(0, "/app")

from domains.bo_mcp.client import BoMcpClient  # noqa: E402

from .objective import OBJECTIVE_NAME, OBJECTIVE_UNIT, PARAMETER_NAMES, canonical_point, evaluate_ackley_6d

MARKER = "akg-eval-7033faa4bb6a4c5f83b5db7865146a1b"
DEFAULT_BACKEND = "botorch"
DEFAULT_RANDOM_SEED = 7033006
DEFAULT_BATCH_SIZE = 5
DEFAULT_INITIAL_DESIGN_SIZE = 15
TARGET_TOTAL_EVALUATIONS = 60
DEFAULT_ACQUISITION_METHOD = "expected_improvement"


def _utcstamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _coerce_status(status: str | None) -> str:
    return (status or "").lower()


def build_intake(*, campaign_name: str, nonce: str) -> dict[str, Any]:
    return {
        "name": campaign_name,
        "description": (
            "Synthetic Ackley 6D benchmark with deterministic Python evaluation; "
            f"marker={MARKER}; nonce={nonce}."
        ),
        "backend": DEFAULT_BACKEND,
        "random_seed": DEFAULT_RANDOM_SEED,
        "batch_size": DEFAULT_BATCH_SIZE,
        "initial_design_size": DEFAULT_INITIAL_DESIGN_SIZE,
        "max_observations": TARGET_TOTAL_EVALUATIONS,
        "acquisition_method": DEFAULT_ACQUISITION_METHOD,
        "parameters": [
            {
                "name": name,
                "type": "continuous",
                "bounds": {"lower": 0.0, "upper": 1.0},
                "description": "Normalized Ackley coordinate",
            }
            for name in PARAMETER_NAMES
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


def _ensure_campaign(
    *,
    client: BoMcpClient,
    campaign_id: str | None,
    artifact_dir: Path,
    nonce: str,
) -> tuple[str, dict[str, Any]]:
    if campaign_id:
        campaign = client.get_campaign(campaign_id)
        name = campaign.get("name") or ""
        if MARKER not in name:
            raise RuntimeError(f"Refusing to use campaign without required marker: {campaign_id}")
        status = _coerce_status(campaign.get("status"))
        if status == "paused":
            logfire.info("Resuming paused campaign", campaign_id=campaign_id)
            client.lifecycle(campaign_id, action="resume")
            campaign = client.get_campaign(campaign_id)
        elif status == "completed":
            logfire.info("Campaign already completed", campaign_id=campaign_id)
        return campaign_id, campaign

    campaign_name = f"ackley-6d-{MARKER}-{nonce[:8]}-{_utcstamp()}"
    intake = build_intake(campaign_name=campaign_name, nonce=nonce)
    validation = client.validate_intake(intake)
    _json_dump(artifact_dir / "intake_validation.json", validation)
    if not validation.get("valid", False):
        raise RuntimeError(f"Intake validation failed: {validation}")
    create_key = client.make_idempotency_key("create", campaign_name, nonce)
    created = client.create_campaign(intake, idempotency_key=create_key)
    if not created.get("success", False):
        raise RuntimeError(f"Campaign creation failed: {created}")
    campaign_id = created["campaign_id"]
    campaign = client.get_campaign(campaign_id)
    _json_dump(artifact_dir / "campaign_create_response.json", created)
    _json_dump(artifact_dir / "campaign_snapshot_initial.json", campaign)
    logfire.info("Created campaign", campaign_id=campaign_id, name=campaign_name)
    return campaign_id, campaign


def _next_action(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> dict[str, Any]:
    action = client.next_action(campaign_id)
    _append_jsonl(
        artifact_dir / "next_action_history.jsonl",
        {
            "timestamp_utc": _utcstamp(),
            **action,
        },
    )
    return action


def _fetch_unique_suggestions(
    *,
    client: BoMcpClient,
    campaign_id: str,
    needed: int,
    seen_points: set[tuple[str, ...]],
    artifact_dir: Path,
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    guard = 0
    while len(chosen) < needed:
        guard += 1
        if guard > 12:
            raise RuntimeError("Unable to collect enough unique suggestions within guard limit")
        pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
        for suggestion in pending:
            suggestion_id = suggestion["suggestion_id"]
            if suggestion_id in chosen_ids:
                continue
            point_key = canonical_point(suggestion["parameter_values"])
            if point_key in seen_points:
                client.update_suggestion_status(suggestion_id, "rejected")
                _append_jsonl(
                    artifact_dir / "duplicate_suggestions_rejected.jsonl",
                    {
                        "timestamp_utc": _utcstamp(),
                        "suggestion_id": suggestion_id,
                        "parameter_values": suggestion["parameter_values"],
                        "reason": "duplicate_point_already_evaluated",
                    },
                )
                continue
            chosen.append(suggestion)
            chosen_ids.add(suggestion_id)
            if len(chosen) == needed:
                return chosen
        shortfall = needed - len(chosen)
        logfire.info("Generating suggestions", campaign_id=campaign_id, batch_size=shortfall)
        client.generate_suggestions(campaign_id, batch_size=shortfall, timeout_s=900.0)
    return chosen


def _build_success_rows(
    *,
    suggestions: list[dict[str, Any]],
    evaluation_index_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    submit_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for offset, suggestion in enumerate(suggestions, start=0):
        evaluation = evaluate_ackley_6d(suggestion["parameter_values"])
        submit_rows.append(
            {
                "suggestion_id": suggestion["suggestion_id"],
                "parameter_values": evaluation.parameter_values,
                "objective_values": {OBJECTIVE_NAME: evaluation.surface_response},
            }
        )
        event_rows.append(
            {
                "evaluation_index": evaluation_index_start + offset,
                "timestamp_utc": _utcstamp(),
                "suggestion_id": suggestion["suggestion_id"],
                "parameter_values": evaluation.parameter_values,
                "objective_values": {OBJECTIVE_NAME: evaluation.surface_response},
                "status": "success",
                "failure_reason": "",
                "raw_response": evaluation.raw_response,
            }
        )
    return submit_rows, event_rows


def _append_failure_event(
    *,
    artifact_dir: Path,
    evaluation_index: int,
    suggestion: dict[str, Any],
    error: Exception,
) -> None:
    _append_jsonl(
        artifact_dir / "evaluation_events.jsonl",
        {
            "evaluation_index": evaluation_index,
            "timestamp_utc": _utcstamp(),
            "suggestion_id": suggestion.get("suggestion_id"),
            "parameter_values": suggestion.get("parameter_values"),
            "objective_values": {},
            "status": "failed",
            "failure_reason": f"{type(error).__name__}: {error}",
            "raw_response": None,
        },
    )


def _compile_results_artifacts(*, artifact_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events = sorted(_load_jsonl(artifact_dir / "evaluation_events.jsonl"), key=lambda row: row["evaluation_index"])
    csv_path = artifact_dir / "evaluated_candidates.csv"
    fieldnames = [
        "evaluation_index",
        *PARAMETER_NAMES,
        OBJECTIVE_NAME,
        "raw_response",
        "status",
        "failure_reason",
        "suggestion_id",
        "parameter_values_json",
        "objective_values_json",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in events:
            parameter_values = row.get("parameter_values") or {}
            objective_values = row.get("objective_values") or {}
            writer.writerow(
                {
                    "evaluation_index": row["evaluation_index"],
                    **{name: parameter_values.get(name, "") for name in PARAMETER_NAMES},
                    OBJECTIVE_NAME: objective_values.get(OBJECTIVE_NAME, ""),
                    "raw_response": row.get("raw_response", ""),
                    "status": row.get("status", ""),
                    "failure_reason": row.get("failure_reason", ""),
                    "suggestion_id": row.get("suggestion_id", ""),
                    "parameter_values_json": json.dumps(parameter_values, sort_keys=True),
                    "objective_values_json": json.dumps(objective_values, sort_keys=True),
                }
            )
    successful = [row for row in events if row.get("status") == "success"]
    attempted = len(events)
    successful_count = len(successful)
    best_row = max(successful, key=lambda row: row["objective_values"][OBJECTIVE_NAME]) if successful else None
    summary = {
        "attempted_evaluations": attempted,
        "successful_evaluations": successful_count,
        "failed_evaluations": attempted - successful_count,
        "best": best_row,
        "results_csv": str(csv_path),
    }
    _json_dump(artifact_dir / "summary.json", summary)
    return events, summary


def run_campaign(
    *,
    nonce: str,
    artifact_dir: Path,
    campaign_id: str | None = None,
    max_new_evaluations: int | None = None,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    client = BoMcpClient.from_env(timeout_s=120.0)
    campaign_id, campaign = _ensure_campaign(
        client=client,
        campaign_id=campaign_id,
        artifact_dir=artifact_dir,
        nonce=nonce,
    )
    _json_dump(artifact_dir / "campaign_snapshot_start.json", campaign)
    status = _coerce_status(campaign.get("status"))
    if status == "completed":
        events, summary = _compile_results_artifacts(artifact_dir=artifact_dir)
        return {"campaign_id": campaign_id, "artifact_dir": str(artifact_dir), "events": events, "summary": summary}

    invocation_budget = max_new_evaluations if max_new_evaluations is not None else TARGET_TOTAL_EVALUATIONS
    new_evaluations = 0
    existing_results = client.get_results(campaign_id)
    seen_points = {canonical_point(row["parameter_values"]) for row in existing_results}

    while new_evaluations < invocation_budget:
        action = _next_action(client, campaign_id, artifact_dir)
        server_results = int(action.get("n_results") or 0)
        remaining_total = TARGET_TOTAL_EVALUATIONS - server_results
        remaining_invocation = invocation_budget - new_evaluations
        if remaining_total <= 0:
            break
        if action.get("action") != "bo_generate_suggestions":
            logfire.info(
                "Server declined further generation",
                campaign_id=campaign_id,
                action=action.get("action"),
                reason=action.get("reason"),
                remaining_total=remaining_total,
            )
            break
        planned_batch = min(DEFAULT_BATCH_SIZE, remaining_total, remaining_invocation)
        suggestions = _fetch_unique_suggestions(
            client=client,
            campaign_id=campaign_id,
            needed=planned_batch,
            seen_points=seen_points,
            artifact_dir=artifact_dir,
        )
        evaluation_index_start = server_results + 1
        try:
            submit_rows, event_rows = _build_success_rows(
                suggestions=suggestions,
                evaluation_index_start=evaluation_index_start,
            )
        except Exception as exc:
            for offset, suggestion in enumerate(suggestions, start=0):
                _append_failure_event(
                    artifact_dir=artifact_dir,
                    evaluation_index=evaluation_index_start + offset,
                    suggestion=suggestion,
                    error=exc,
                )
                client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
            raise
        submit_key = client.make_idempotency_key(
            "submit",
            campaign_id,
            str(evaluation_index_start),
            *[row["suggestion_id"] for row in event_rows],
        )
        submitted = client.submit_results(
            campaign_id,
            results=submit_rows,
            idempotency_key=submit_key,
            force=False,
        )
        if not submitted.get("success", False):
            raise RuntimeError(f"Result submission failed: {submitted}")
        result_ids = submitted.get("result_ids") or []
        for idx, row in enumerate(event_rows):
            if idx < len(result_ids):
                row["result_id"] = result_ids[idx]
            _append_jsonl(artifact_dir / "evaluation_events.jsonl", row)
            seen_points.add(canonical_point(row["parameter_values"]))
        new_evaluations += len(event_rows)
        logfire.info(
            "Submitted synthetic Ackley batch",
            campaign_id=campaign_id,
            batch_size=len(event_rows),
            total_new_evaluations=new_evaluations,
            best_surface_in_batch=max(row["objective_values"][OBJECTIVE_NAME] for row in event_rows),
        )

    final_campaign = client.get_campaign(campaign_id)
    final_status = _coerce_status(final_campaign.get("status"))
    if final_status in {"running", "created"}:
        paused = client.lifecycle(campaign_id, action="pause")
        _json_dump(artifact_dir / "campaign_pause_response.json", paused)
        final_campaign = client.get_campaign(campaign_id)
    _json_dump(artifact_dir / "campaign_snapshot_final.json", final_campaign)
    events, summary = _compile_results_artifacts(artifact_dir=artifact_dir)
    return {
        "campaign_id": campaign_id,
        "artifact_dir": str(artifact_dir),
        "events": events,
        "summary": summary,
        "campaign_status": final_campaign.get("status"),
    }
