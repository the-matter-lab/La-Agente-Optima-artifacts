from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluator import build_result_payload, evaluate_candidate
from .intake import DEFAULT_BACKEND, DEFAULT_INITIAL_DESIGN_SIZE, DEFAULT_RANDOM_SEED, build_intake
from .reporting import RESULTS_JSONL, RUN_LOG, append_jsonl, ensure_artifact_dir, write_summary_files
from .search_space import CACHE_BUSTER_NONCE, CAMPAIGN_MARKER, OBJECTIVE_NAME, TOTAL_BUDGET, build_campaign_name, parameter_key


@dataclass
class RunConfig:
    requested_campaign_id: str | None = None
    campaign_label: str = "main"
    artifact_root: str = "artifacts/ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2"
    stop_file: str = "STOP"
    invocation_attempt_budget: int = TOTAL_BUDGET
    poll_s: int = 180
    heartbeat_s: int = 1800
    random_seed: int = DEFAULT_RANDOM_SEED
    backend: str = DEFAULT_BACKEND
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE


ATTEMPTED_STATUSES = {"completed", "expired"}


def _emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"ackley_campaign_{log_path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_campaign_name(payload: dict[str, Any]) -> str:
    name = payload.get("name")
    if isinstance(name, str):
        return name
    nested = payload.get("campaign")
    if isinstance(nested, dict) and isinstance(nested.get("name"), str):
        return nested["name"]
    return json.dumps(payload, sort_keys=True)


def _create_or_attach_campaign(client: BoMcpClient, config: RunConfig, logger: logging.Logger) -> str:
    if config.requested_campaign_id:
        campaign = client.get_campaign(config.requested_campaign_id)
        campaign_name = _extract_campaign_name(campaign)
        if CAMPAIGN_MARKER not in campaign_name:
            raise ValueError(
                f"Campaign {config.requested_campaign_id} is missing required marker {CAMPAIGN_MARKER}."
            )
        _emit("EVENT", f"Attached to owned campaign {config.requested_campaign_id}.")
        print(f"BO_MCP_CAMPAIGN_ID={config.requested_campaign_id}", flush=True)
        return config.requested_campaign_id

    campaign_name = build_campaign_name(config.campaign_label)
    intake = build_intake(
        campaign_name,
        backend=config.backend,
        random_seed=config.random_seed,
        initial_design_size=config.initial_design_size,
    )
    validation = client.validate_intake(intake)
    logger.info("validate_intake=%s", validation)
    if not validation.get("valid", validation.get("success", False)):
        raise RuntimeError(f"Campaign intake validation failed: {validation}")
    response = client.create_campaign(
        intake,
        idempotency_key=client.make_idempotency_key("create", campaign_name, CACHE_BUSTER_NONCE),
    )
    if not response.get("success", False):
        raise RuntimeError(f"Campaign creation failed: {response}")
    campaign_id = str(response["campaign_id"])
    _emit("EVENT", f"Created campaign {campaign_id} ({campaign_name}).")
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
    return campaign_id


def _resume_if_needed(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any]:
    decision = client.next_action(campaign_id)
    status = _normalize_status(decision.get("status"))
    logger.info("initial_next_action=%s", decision)
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        _emit("EVENT", f"Resumed paused campaign {campaign_id}.")
        decision = client.next_action(campaign_id)
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        _emit("EVENT", f"Reopened completed campaign {campaign_id}.")
        decision = client.next_action(campaign_id)
    return decision


def _pause_if_running(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> None:
    try:
        decision = client.next_action(campaign_id)
    except Exception as exc:  # pragma: no cover
        logger.warning("pause query failed: %s", exc)
        return
    status = _normalize_status(decision.get("status"))
    if status in {"paused", "completed", "terminated"}:
        return
    client.lifecycle(campaign_id, action="pause")
    _emit("EVENT", f"Paused campaign {campaign_id}.")


def _query_progress(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    suggestions = client.query_suggestions(campaign_id, status_filter=None, limit=500)
    attempted = 0
    successful = 0
    seen_parameter_keys: set[str] = set()
    for suggestion in suggestions:
        status = _normalize_status(suggestion.get("status"))
        parameter_values = suggestion.get("parameter_values")
        if isinstance(parameter_values, dict) and status in ATTEMPTED_STATUSES:
            seen_parameter_keys.add(parameter_key(parameter_values))
        if status in ATTEMPTED_STATUSES:
            attempted += 1
        if status == "completed":
            successful += 1
    return {
        "attempted": attempted,
        "successful": successful,
        "seen_parameter_keys": seen_parameter_keys,
    }


def _write_incremental_summary(artifact_dir: Path, campaign_id: str) -> dict[str, Any]:
    summary = write_summary_files(artifact_dir, campaign_id)
    _emit(
        "EVENT",
        (
            f"Updated artifacts in {artifact_dir}. attempted={summary['attempted_evaluations']} "
            f"successful={summary['successful_evaluations']}"
        ),
    )
    return summary


def run_campaign(client: BoMcpClient, config: RunConfig) -> dict[str, Any]:
    bootstrap_logger = logging.getLogger("ackley_campaign_bootstrap")
    bootstrap_logger.handlers.clear()

    campaign_id = _create_or_attach_campaign(client, config, bootstrap_logger)
    artifact_dir = ensure_artifact_dir(config.artifact_root, campaign_id)
    logger = _setup_logger(artifact_dir / RUN_LOG)
    logfire.info("ackley campaign starting", campaign_id=campaign_id, artifact_dir=str(artifact_dir))
    logger.info("artifact_dir=%s", artifact_dir)
    _emit("EVENT", f"Artifacts directory: {artifact_dir}")

    _resume_if_needed(client, campaign_id, logger)
    attempts_this_run = 0
    last_heartbeat = 0.0
    summary = _write_incremental_summary(artifact_dir, campaign_id)

    try:
        while attempts_this_run < config.invocation_attempt_budget:
            if Path(config.stop_file).exists():
                Path(config.stop_file).unlink()
                _emit("EVENT", f"Stop file detected and cleared at {config.stop_file}.")
                break

            progress = _query_progress(client, campaign_id)
            attempted_total = int(progress["attempted"])
            successful_total = int(progress["successful"])
            seen_parameter_keys = set(progress["seen_parameter_keys"])

            if attempted_total >= TOTAL_BUDGET:
                _emit("EVENT", f"Attempt budget reached at {attempted_total}/{TOTAL_BUDGET}.")
                break

            now = time.time()
            if now - last_heartbeat >= config.heartbeat_s:
                _emit(
                    "HEARTBEAT",
                    (
                        f"campaign_id={campaign_id} attempted={attempted_total} successful={successful_total} "
                        f"remaining={TOTAL_BUDGET - attempted_total}"
                    ),
                )
                last_heartbeat = now

            decision = client.next_action(campaign_id)
            logger.info("next_action=%s", decision)
            if decision.get("action") != "bo_generate_suggestions":
                _emit(
                    "EVENT",
                    (
                        f"Server requested stop: action={decision.get('action')} "
                        f"reason={decision.get('reason')} status={decision.get('status')}"
                    ),
                )
                break

            response = client.generate_suggestions(
                campaign_id,
                batch_size=1,
                timeout_s=max(float(config.poll_s), 300.0),
            )
            logger.info("generate_suggestions=%s", response)
            suggestions = list(response.get("suggestions") or [])
            if not response.get("success", False) or not suggestions:
                _emit("ALERT", f"Suggestion generation failed or returned no candidates: {response}")
                break

            suggestion = suggestions[0]
            suggestion_id = str(suggestion["suggestion_id"])
            parameter_values = dict(suggestion["parameter_values"])
            suggestion_key = parameter_key(parameter_values)
            if suggestion_key in seen_parameter_keys:
                client.update_suggestion_status(suggestion_id, "rejected")
                _emit("EVENT", f"Rejected duplicate suggestion {suggestion_id} without evaluation.")
                continue

            evaluation_index = attempted_total + 1
            record = evaluate_candidate(
                parameter_values,
                evaluation_index=evaluation_index,
                suggestion_id=suggestion_id,
            )
            logger.info("evaluation_record=%s", record)

            if record["status"] == "completed":
                submission = client.submit_results(
                    campaign_id,
                    results=[build_result_payload(record)],
                    idempotency_key=client.make_idempotency_key(
                        "submit",
                        campaign_id,
                        suggestion_id,
                        str(evaluation_index),
                    ),
                )
                logger.info("submit_results=%s", submission)
                if not submission.get("success", False):
                    raise RuntimeError(f"Result submission failed: {submission}")
            else:
                client.update_suggestion_status(suggestion_id, "expired")
                logger.info("expired_failed_suggestion=%s", suggestion_id)

            append_jsonl(artifact_dir / RESULTS_JSONL, record)
            attempts_this_run += 1
            summary = _write_incremental_summary(artifact_dir, campaign_id)
            if record["status"] == "completed":
                _emit(
                    "RESULT",
                    (
                        f"evaluation_index={record['evaluation_index']} status=completed "
                        f"raw_response={record['raw_response']:.16f} "
                        f"surface_response={record['objective_values'][OBJECTIVE_NAME]:.16f} "
                        f"parameter_values={json.dumps(record['parameter_values'], sort_keys=True)}"
                    ),
                )
            else:
                _emit(
                    "RESULT",
                    (
                        f"evaluation_index={record['evaluation_index']} status=failed "
                        f"failure_reason={record['failure_reason']} "
                        f"parameter_values={json.dumps(record['parameter_values'], sort_keys=True)}"
                    ),
                )

        summary = _write_incremental_summary(artifact_dir, campaign_id)
        return summary
    finally:
        _pause_if_running(client, campaign_id, logger)
        logfire.info("ackley campaign finished", campaign_id=campaign_id)
