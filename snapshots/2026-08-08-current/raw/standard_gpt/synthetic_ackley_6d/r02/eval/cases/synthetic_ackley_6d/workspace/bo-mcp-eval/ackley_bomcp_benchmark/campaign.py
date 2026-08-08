from __future__ import annotations

import contextlib
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import logfire

from .evaluator import evaluate_candidate
from .intake import CAMPAIGN_MARKER, OBJECTIVE_NAME, TOTAL_ATTEMPT_BUDGET, build_intake
from .reporting import append_evaluation_row, emit_tag, ensure_artifact_dir, write_campaign_ref
from .search_space import canonical_point

LOGGER = logging.getLogger(__name__)


def _new_idempotency_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _configure_file_logging(artifact_dir: Path) -> Path:
    log_path = artifact_dir / "run.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(
        isinstance(existing, logging.FileHandler)
        and Path(getattr(existing, "baseFilename", "")) == log_path
        for existing in root.handlers
    ):
        root.addHandler(handler)
    return log_path


def _count_existing_results(client: Any, campaign_id: str) -> int:
    return len(client.get_results(campaign_id))


def _count_recorded_attempts(artifact_dir: Path) -> int:
    evaluations_path = artifact_dir / "evaluations.jsonl"
    if not evaluations_path.exists():
        return 0
    with evaluations_path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _budget_is_exhausted(*, completed_results_count: int, recorded_attempt_count: int) -> bool:
    return max(completed_results_count, recorded_attempt_count) >= TOTAL_ATTEMPT_BUDGET


def _ensure_owned_campaign(client: Any, campaign_id: str) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    if CAMPAIGN_MARKER not in campaign["name"]:
        raise ValueError(
            f"Refusing to operate on campaign {campaign_id} because its name lacks marker {CAMPAIGN_MARKER}."
        )
    return campaign


def _prepare_campaign(client: Any, requested_campaign_id: str | None) -> tuple[dict[str, Any], bool]:
    if requested_campaign_id:
        campaign = _ensure_owned_campaign(client, requested_campaign_id)
        existing_results = _count_existing_results(client, requested_campaign_id)
        status = campaign.get("status")
        if status == "paused" and existing_results < TOTAL_ATTEMPT_BUDGET:
            client.lifecycle(requested_campaign_id, action="resume")
            campaign = client.get_campaign(requested_campaign_id)
        elif status == "completed" and existing_results < TOTAL_ATTEMPT_BUDGET:
            client.lifecycle(requested_campaign_id, action="reopen")
            campaign = client.get_campaign(requested_campaign_id)
        emit_tag(
            "EVENT",
            {
                "kind": "campaign_ready",
                "campaign_id": campaign["id"],
                "status": campaign.get("status"),
                "existing_results": existing_results,
                "budget_exhausted": existing_results >= TOTAL_ATTEMPT_BUDGET,
            },
        )
        return campaign, False

    intake = build_intake()
    client.validate_intake(intake)
    created = client.create_campaign(intake, idempotency_key=_new_idempotency_key("create"))
    campaign_id = created["campaign_id"]
    campaign = _ensure_owned_campaign(client, campaign_id)
    emit_tag(
        "EVENT",
        {
            "kind": "campaign_created",
            "campaign_id": campaign_id,
            "campaign_name": campaign["name"],
            "idempotency_replay": bool(created.get("idempotency_replay")),
        },
    )
    return campaign, True


def _next_pending_suggestion(client: Any, campaign_id: str) -> dict[str, Any] | None:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
    return pending[0] if pending else None


def run_campaign(
    *,
    client: Any,
    requested_campaign_id: str | None,
    invocation_attempt_budget: int,
    stop_file: str,
    heartbeat_s: int,
    artifact_root: str,
) -> dict[str, Any]:
    campaign, created = _prepare_campaign(client, requested_campaign_id)
    campaign_id = campaign["id"]
    artifact_dir = ensure_artifact_dir(artifact_root, campaign_id)
    log_path = _configure_file_logging(artifact_dir)
    write_campaign_ref(artifact_dir, campaign_id=campaign_id, campaign_name=campaign["name"])
    LOGGER.info("Starting Ackley campaign run for %s", campaign_id)
    logfire.info("ackley campaign run started", campaign_id=campaign_id, created=created)

    observed_results = client.get_results(campaign_id)
    attempted_points = {canonical_point(result["parameter_values"]) for result in observed_results}
    initial_count = len(observed_results)
    completed_results_count = initial_count
    recorded_attempt_count = _count_recorded_attempts(artifact_dir)
    attempts_this_run = 0
    next_evaluation_index = max(initial_count, recorded_attempt_count) + 1
    last_heartbeat = 0.0

    emit_tag(
        "EVENT",
        {
            "kind": "run_started",
            "campaign_id": campaign_id,
            "campaign_name": campaign["name"],
            "existing_results": initial_count,
            "recorded_attempts": recorded_attempt_count,
            "artifact_dir": str(artifact_dir),
            "log_path": str(log_path),
        },
    )

    while attempts_this_run < invocation_attempt_budget:
        if _budget_is_exhausted(
            completed_results_count=completed_results_count,
            recorded_attempt_count=recorded_attempt_count,
        ):
            emit_tag(
                "EVENT",
                {
                    "kind": "budget_exhausted",
                    "campaign_id": campaign_id,
                    "completed_results": completed_results_count,
                    "recorded_attempts": recorded_attempt_count,
                    "budget": TOTAL_ATTEMPT_BUDGET,
                },
            )
            break

        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            emit_tag(
                "HEARTBEAT",
                {
                    "campaign_id": campaign_id,
                    "attempts_this_run": attempts_this_run,
                    "successful_results": completed_results_count,
                    "recorded_attempts": recorded_attempt_count,
                },
            )
            last_heartbeat = now

        stop_path = Path(stop_file)
        if stop_path.exists():
            stop_path.unlink()
            emit_tag("EVENT", {"kind": "stop_file_detected", "campaign_id": campaign_id, "stop_file": str(stop_path)})
            break

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            emit_tag(
                "EVENT",
                {
                    "kind": "next_action_stop",
                    "campaign_id": campaign_id,
                    "action": decision.get("action"),
                    "decision": decision,
                },
            )
            break

        suggestion = _next_pending_suggestion(client, campaign_id)
        if suggestion is None:
            generated = client.generate_suggestions(campaign_id, batch_size=1)
            suggestions = generated.get("suggestions", [])
            if not suggestions:
                emit_tag(
                    "ALERT",
                    {
                        "kind": "empty_generation",
                        "campaign_id": campaign_id,
                        "response": generated,
                    },
                )
                break
            suggestion = suggestions[0]

        suggestion_id = suggestion["suggestion_id"]
        parameter_values = suggestion["parameter_values"]
        point_key = canonical_point(parameter_values)
        if point_key in attempted_points:
            client.update_suggestion_status(suggestion_id, "rejected")
            emit_tag(
                "ALERT",
                {
                    "kind": "duplicate_suggestion_rejected",
                    "campaign_id": campaign_id,
                    "suggestion_id": suggestion_id,
                    "parameter_values": parameter_values,
                },
            )
            continue

        row = evaluate_candidate(
            campaign_id=campaign_id,
            evaluation_index=next_evaluation_index,
            parameter_values=parameter_values,
            suggestion_id=suggestion_id,
        )
        attempts_this_run += 1
        recorded_attempt_count += 1
        next_evaluation_index += 1
        attempted_points.add(point_key)

        if row["status"] == "completed":
            client.submit_results(
                campaign_id,
                results=[
                    {
                        "suggestion_id": suggestion_id,
                        "parameter_values": row["parameter_values"],
                        "objective_values": row["objective_values"],
                        "metadata": {
                            "notes": "Deterministic local Ackley 6D synthetic benchmark.",
                            "batch_ref": "ackley-local",
                        },
                    }
                ],
                idempotency_key=_new_idempotency_key("submit"),
                force=False,
            )
            append_evaluation_row(artifact_dir, row)
            completed_results_count += 1
            emit_tag(
                "RESULT",
                {
                    "campaign_id": campaign_id,
                    "evaluation_index": row["evaluation_index"],
                    "suggestion_id": suggestion_id,
                    "status": row["status"],
                    "surface_response": row["objective_values"][OBJECTIVE_NAME],
                    "raw_response": row["raw_response"],
                    "parameter_values": row["parameter_values"],
                },
            )
            continue

        client.update_suggestion_status(suggestion_id, "rejected")
        append_evaluation_row(artifact_dir, row)
        emit_tag(
            "ALERT",
            {
                "kind": "evaluation_failed",
                "campaign_id": campaign_id,
                "evaluation_index": row["evaluation_index"],
                "suggestion_id": suggestion_id,
                "failure_reason": row["failure_reason"],
            },
        )

    final_campaign = client.get_campaign(campaign_id)
    final_results_count = len(client.get_results(campaign_id))
    final_recorded_attempt_count = _count_recorded_attempts(artifact_dir)
    status = final_campaign.get("status")
    if status == "running":
        with contextlib.suppress(Exception):
            client.lifecycle(campaign_id, action="pause")
            final_campaign = client.get_campaign(campaign_id)
            status = final_campaign.get("status")

    summary = {
        "campaign_id": campaign_id,
        "campaign_name": final_campaign["name"],
        "artifact_dir": str(artifact_dir),
        "log_path": str(log_path),
        "evaluations_jsonl": str(artifact_dir / "evaluations.jsonl"),
        "evaluations_csv": str(artifact_dir / "evaluations.csv"),
        "attempts_this_run": attempts_this_run,
        "recorded_attempts": final_recorded_attempt_count,
        "total_results": final_results_count,
        "status": status,
    }
    emit_tag("EVENT", {"kind": "run_finished", **summary})
    LOGGER.info("Finished Ackley campaign run for %s", campaign_id)
    logfire.info("ackley campaign run finished", **summary)
    return summary
