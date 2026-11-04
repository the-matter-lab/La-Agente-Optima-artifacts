from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
import requests
from domains.bo_mcp.client import BoMcpClient

from .evaluation import build_attempt_record, evaluate_candidate
from .intake import CHAT_TRACE_ID, OWNERSHIP_MARKER, build_intake, ensure_owned_campaign
from .reporting import append_jsonl, build_summary, ensure_artifact_dir, load_attempts, write_json
from .search_space import canonicalize_parameter_values, format_parameters

LOGGER = logging.getLogger(__name__)


@dataclass
class RunConfig:
    campaign_id: str | None = None
    max_attempts: int = 60
    poll_s: int = 180
    heartbeat_s: int = 1800
    stop_file: str = "STOP"
    artifacts_dir: str = "artifacts/direct_arylation_yield_baybe"
    oracle_timeout_s: float = 60.0
    diagnostics_timeout_s: float = 600.0
    dry_run: bool = False


def emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def _idempotency_key(prefix: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _create_or_resume_campaign(client: BoMcpClient, config: RunConfig) -> dict[str, Any]:
    if config.campaign_id:
        campaign = client.get_campaign(config.campaign_id)
        ensure_owned_campaign(campaign)
        status = str(campaign.get("status", "")).lower()
        if status == "paused":
            client.lifecycle(config.campaign_id, action="resume")
            emit("EVENT", f"resumed campaign_id={config.campaign_id} trace={CHAT_TRACE_ID}")
            return client.get_campaign(config.campaign_id)
        if status == "completed":
            client.lifecycle(config.campaign_id, action="reopen")
            emit("EVENT", f"reopened campaign_id={config.campaign_id} trace={CHAT_TRACE_ID}")
            return client.get_campaign(config.campaign_id)
        if status == "running":
            emit("EVENT", f"using running campaign_id={config.campaign_id} trace={CHAT_TRACE_ID}")
            return campaign
        raise RuntimeError(f"Campaign {config.campaign_id} is in unsupported status {status!r}.")

    intake = build_intake(max_attempts=config.max_attempts)
    client.validate_intake(intake)
    response = client.create_campaign(intake, idempotency_key=_idempotency_key("create", intake))
    campaign_id = response["campaign_id"]
    campaign = client.get_campaign(campaign_id)
    ensure_owned_campaign(campaign)
    emit("EVENT", f"created campaign_id={campaign_id} name={campaign['name']} trace={CHAT_TRACE_ID}")
    return campaign


def _get_pending_suggestion(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    pending = client.query_suggestions(campaign_id, status_filter="pending")
    if pending:
        return pending[0]
    try:
        generated = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=900.0)
    except Exception:
        pending = client.query_suggestions(campaign_id, status_filter="pending")
        if pending:
            return pending[0]
        raise
    suggestions = generated.get("suggestions") or []
    if not suggestions:
        raise RuntimeError(f"No suggestions returned for campaign {campaign_id}: {generated}")
    return suggestions[0]


def _maybe_stop_requested(config: RunConfig) -> bool:
    stop_path = Path(config.stop_file)
    if stop_path.exists():
        stop_path.unlink()
        emit("EVENT", f"stop file detected and cleared at {stop_path} trace={CHAT_TRACE_ID}")
        return True
    return False


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    ensure_owned_campaign(campaign)
    if str(campaign.get("status", "")).lower() == "running":
        client.lifecycle(campaign_id, action="pause")
        campaign = client.get_campaign(campaign_id)
        emit("EVENT", f"paused campaign_id={campaign_id} trace={CHAT_TRACE_ID}")
    return campaign


def run_campaign(config: RunConfig) -> dict[str, Any]:
    artifacts_dir = ensure_artifact_dir(Path(config.artifacts_dir))
    attempts_path = artifacts_dir / "attempts.jsonl"
    summary_path = artifacts_dir / "summary.json"
    campaign_path = artifacts_dir / "campaign.json"
    diagnostics_path = artifacts_dir / "diagnostics.json"
    metadata_path = artifacts_dir / "run_metadata.json"

    metadata = {
        "chat_trace_id": CHAT_TRACE_ID,
        "ownership_marker": OWNERSHIP_MARKER,
        "dry_run": config.dry_run,
        "max_attempts": config.max_attempts,
    }
    write_json(metadata_path, metadata)

    if config.dry_run:
        summary = build_summary(campaign=None, attempts=load_attempts(attempts_path), diagnostics=None, invocation_attempts=0)
        write_json(summary_path, summary)
        emit("EVENT", f"dry run complete artifacts_dir={artifacts_dir} trace={CHAT_TRACE_ID}")
        return summary

    api_url = os.environ["DIRECT_ARYLATION_API_URL"]
    client = BoMcpClient.from_env()
    campaign = _create_or_resume_campaign(client, config)
    campaign_id = str(campaign["id"])
    write_json(campaign_path, campaign)
    emit(
        "EVENT",
        f"starting campaign loop campaign_id={campaign_id} max_attempts={config.max_attempts} poll_s={config.poll_s} heartbeat_s={config.heartbeat_s} trace={CHAT_TRACE_ID}",
    )

    invocation_attempts = 0
    last_heartbeat = time.monotonic()
    session = requests.Session()

    try:
        while invocation_attempts < config.max_attempts:
            if _maybe_stop_requested(config):
                break

            if time.monotonic() - last_heartbeat >= config.heartbeat_s:
                emit(
                    "HEARTBEAT",
                    f"campaign_id={campaign_id} attempted_this_run={invocation_attempts}/{config.max_attempts} trace={CHAT_TRACE_ID}",
                )
                last_heartbeat = time.monotonic()

            decision = client.next_action(campaign_id)
            LOGGER.info("next_action=%s", decision)
            if decision.get("action") != "bo_generate_suggestions":
                emit(
                    "EVENT",
                    f"stopping on server decision action={decision.get('action')} reason={decision.get('reason')} campaign_id={campaign_id} trace={CHAT_TRACE_ID}",
                )
                break

            suggestion = _get_pending_suggestion(client, campaign_id)
            suggestion_id = str(suggestion["suggestion_id"])
            parameter_values = canonicalize_parameter_values(suggestion["parameter_values"])
            LOGGER.info("evaluating suggestion_id=%s parameters=%s", suggestion_id, parameter_values)

            invocation_attempts += 1
            evaluation = evaluate_candidate(
                api_url=api_url,
                parameter_values=parameter_values,
                timeout_s=config.oracle_timeout_s,
                session=session,
            )
            record = build_attempt_record(
                attempt_index=invocation_attempts,
                campaign_id=campaign_id,
                suggestion_id=suggestion_id,
                evaluation=evaluation,
            )

            if evaluation.status == "oracle_success":
                submission = {
                    "parameter_values": parameter_values,
                    "objective_values": evaluation.objective_values,
                    "suggestion_id": suggestion_id,
                }
                try:
                    client.submit_results(
                        campaign_id,
                        results=[submission],
                        idempotency_key=_idempotency_key("submit", submission),
                        force=True,
                    )
                    record["status"] = "submitted"
                except Exception as exc:
                    record["status"] = "submission_failed"
                    record["error"] = str(exc)
                    append_jsonl(attempts_path, record)
                    emit(
                        "ALERT",
                        f"submission failed attempt={invocation_attempts} campaign_id={campaign_id} suggestion_id={suggestion_id} trace={CHAT_TRACE_ID}",
                    )
                    emit(
                        "RESULT",
                        f"attempt={invocation_attempts} status=submission_failed yield={evaluation.objective_values['yield']:.4f} {format_parameters(parameter_values)}",
                    )
                    raise
                append_jsonl(attempts_path, record)
                emit(
                    "RESULT",
                    f"attempt={invocation_attempts} status=submitted yield={evaluation.objective_values['yield']:.4f} {format_parameters(parameter_values)}",
                )
            else:
                append_jsonl(attempts_path, record)
                client.update_suggestion_status(suggestion_id, "rejected")
                emit(
                    "ALERT",
                    f"oracle failure attempt={invocation_attempts} status={evaluation.status} suggestion_id={suggestion_id} trace={CHAT_TRACE_ID}",
                )
                emit(
                    "RESULT",
                    f"attempt={invocation_attempts} status={evaluation.status} {format_parameters(parameter_values)}",
                )

        try:
            diagnostics = client.get_diagnostics(campaign_id, timeout_s=config.diagnostics_timeout_s)
            write_json(diagnostics_path, diagnostics)
        except Exception as exc:
            diagnostics = {"error": str(exc)}
            write_json(diagnostics_path, diagnostics)
            emit("ALERT", f"diagnostics collection failed campaign_id={campaign_id} trace={CHAT_TRACE_ID}")
    finally:
        campaign = _pause_if_running(client, campaign_id)
        write_json(campaign_path, campaign)

    attempts = load_attempts(attempts_path)
    summary = build_summary(
        campaign=campaign,
        attempts=attempts,
        diagnostics=json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else None,
        invocation_attempts=invocation_attempts,
    )
    write_json(summary_path, summary)
    emit(
        "EVENT",
        f"run complete campaign_id={campaign_id} attempts_this_run={invocation_attempts} total_recorded_attempts={len(attempts)} trace={CHAT_TRACE_ID}",
    )
    return summary
