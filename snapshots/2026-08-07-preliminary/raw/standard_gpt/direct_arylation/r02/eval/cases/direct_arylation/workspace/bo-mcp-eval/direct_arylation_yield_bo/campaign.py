from __future__ import annotations

import logging
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
import requests
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .evaluator import EvaluationFailure, evaluate_candidate
from .intake import build_intake
from .reporting import append_jsonl, load_jsonl, summarize_attempts, write_json
from .search_space import (
    CACHE_BUSTER_NONCE,
    CAMPAIGN_SLUG,
    DEFAULT_CAMPAIGN_MAX_OBSERVATIONS,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RANDOM_SEED,
    OBJECTIVE_NAME,
    OWNERSHIP_MARKER,
    candidate_signature,
    canonical_candidate,
)


@dataclass(slots=True)
class RunConfig:
    campaign_id: str | None
    artifact_root: Path
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    campaign_max_observations: int = DEFAULT_CAMPAIGN_MAX_OBSERVATIONS
    random_seed: int = DEFAULT_RANDOM_SEED
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE
    poll_s: float = 180.0
    heartbeat_s: float = 1800.0
    request_timeout_s: float = 60.0
    stop_file: Path = Path("STOP")


@dataclass(slots=True)
class RuntimePaths:
    artifact_dir: Path
    attempts_jsonl: Path
    summary_json: Path
    bo_results_json: Path
    diagnostics_json: Path
    campaign_json: Path
    campaign_id_txt: Path
    log_file: Path
    config_json: Path


def _stdout(message: str) -> None:
    print(message, flush=True)


def _event(message: str) -> None:
    _stdout(f"[EVENT] {message} | nonce={CACHE_BUSTER_NONCE}")


def _alert(message: str) -> None:
    _stdout(f"[ALERT] {message} | nonce={CACHE_BUSTER_NONCE}")


def _result(message: str) -> None:
    _stdout(f"[RESULT] {message} | nonce={CACHE_BUSTER_NONCE}")


def _heartbeat(message: str) -> None:
    _stdout(f"[HEARTBEAT] {message} | nonce={CACHE_BUSTER_NONCE}")


def _setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(CAMPAIGN_SLUG)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _require_direct_arylation_api_url() -> str:
    api_url = os.getenv("DIRECT_ARYLATION_API_URL")
    if not api_url:
        raise RuntimeError("DIRECT_ARYLATION_API_URL is required.")
    return api_url.rstrip("/")


def _ensure_marker(campaign: dict[str, Any]) -> None:
    name = str(campaign.get("name", ""))
    if OWNERSHIP_MARKER not in name:
        raise RuntimeError(
            "Refusing to use campaign without required ownership marker "
            f"{OWNERSHIP_MARKER}: {name!r}"
        )


def _artifact_dir(root: Path, campaign_id: str) -> Path:
    return root / campaign_id


def _runtime_paths(root: Path, campaign_id: str) -> RuntimePaths:
    artifact_dir = _artifact_dir(root, campaign_id)
    return RuntimePaths(
        artifact_dir=artifact_dir,
        attempts_jsonl=artifact_dir / "attempts.jsonl",
        summary_json=artifact_dir / "summary.json",
        bo_results_json=artifact_dir / "bo_results.json",
        diagnostics_json=artifact_dir / "diagnostics.json",
        campaign_json=artifact_dir / "campaign.json",
        campaign_id_txt=artifact_dir / "campaign_id.txt",
        log_file=artifact_dir / "run.log",
        config_json=artifact_dir / "run_config.json",
    )


def _write_runtime_config(paths: RuntimePaths, config: RunConfig) -> None:
    payload = {
        "cache_buster_nonce": CACHE_BUSTER_NONCE,
        "campaign_id": config.campaign_id,
        "artifact_root": str(config.artifact_root),
        "max_attempts": config.max_attempts,
        "campaign_max_observations": config.campaign_max_observations,
        "random_seed": config.random_seed,
        "initial_design_size": config.initial_design_size,
        "poll_s": config.poll_s,
        "heartbeat_s": config.heartbeat_s,
        "request_timeout_s": config.request_timeout_s,
        "stop_file": str(config.stop_file),
        "hostname": socket.gethostname(),
    }
    write_json(paths.config_json, payload)


def _persist_snapshot(
    *,
    client: BoMcpClient,
    campaign_id: str,
    paths: RuntimePaths,
    attempts: list[dict[str, Any]],
    logger: logging.Logger,
) -> None:
    summary = summarize_attempts(campaign_id, attempts)
    write_json(paths.summary_json, summary)
    try:
        campaign = client.get_campaign(campaign_id)
        _ensure_marker(campaign)
        write_json(paths.campaign_json, campaign)
    except Exception as exc:  # pragma: no cover - nonfatal artifact refresh
        logger.warning("Unable to refresh campaign snapshot: %s", exc)
    try:
        results = client.get_results(campaign_id)
        write_json(paths.bo_results_json, results)
    except Exception as exc:  # pragma: no cover - nonfatal artifact refresh
        logger.warning("Unable to refresh BO results snapshot: %s", exc)


def _normalize_attempt_count(attempts: list[dict[str, Any]]) -> int:
    return len(attempts)


def _ensure_campaign(client: BoMcpClient, config: RunConfig) -> str:
    if config.campaign_id:
        campaign = client.get_campaign(config.campaign_id)
        _ensure_marker(campaign)
        return str(campaign["id"])
    if config.campaign_max_observations < config.max_attempts:
        raise RuntimeError(
            "campaign_max_observations must be at least max_attempts for a fresh campaign. "
            f"Got campaign_max_observations={config.campaign_max_observations} and max_attempts={config.max_attempts}."
        )
    intake = build_intake(
        max_observations=config.campaign_max_observations,
        random_seed=config.random_seed,
        initial_design_size=config.initial_design_size,
    )
    validation = client.validate_intake(intake)
    if not validation.get("valid", False):
        raise RuntimeError(f"Campaign intake validation failed: {validation}")
    response = client.create_campaign(
        intake,
        idempotency_key=str(uuid.uuid4()),
    )
    campaign_id = str(response["campaign_id"])
    campaign = client.get_campaign(campaign_id)
    _ensure_marker(campaign)
    return campaign_id


def _resume_if_needed(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    _ensure_marker(campaign)
    status = str(campaign.get("status", ""))
    if status == "paused":
        logger.info("Resuming paused campaign %s", campaign_id)
        client.lifecycle(campaign_id, action="resume")
        campaign = client.get_campaign(campaign_id)
    elif status == "completed":
        logger.info("Reopening completed campaign %s", campaign_id)
        client.lifecycle(campaign_id, action="reopen")
        campaign = client.get_campaign(campaign_id)
    return campaign


def _pending_or_new_suggestion(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any] | None:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=1)
    if pending:
        logger.info("Using existing pending suggestion %s", pending[0].get("suggestion_id"))
        return pending[0]
    try:
        generated = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=900.0)
    except BoMcpOperationError as exc:
        logger.warning("Suggestion generation rejected for campaign %s: %s", campaign_id, exc.payload)
        errors = exc.payload.get("errors") or [str(exc)]
        _alert(
            f"bo-generate-rejected campaign_id={campaign_id} reason={' ; '.join(str(item) for item in errors)}"
        )
        return None
    suggestions = generated.get("suggestions", [])
    if not suggestions:
        raise RuntimeError(f"No suggestions returned: {generated}")
    return suggestions[0]


def _submit_result(
    client: BoMcpClient,
    campaign_id: str,
    suggestion: dict[str, Any],
    objective_value: float,
    logger: logging.Logger,
) -> dict[str, Any]:
    payload = {
        "parameter_values": canonical_candidate(dict(suggestion["parameter_values"])),
        "objective_values": {OBJECTIVE_NAME: float(objective_value)},
        "suggestion_id": suggestion["suggestion_id"],
        "metadata": {
            "experiment_id": str(uuid.uuid4()),
            "batch_ref": CACHE_BUSTER_NONCE,
            "notes": f"direct arylation oracle evaluation; nonce={CACHE_BUSTER_NONCE}",
            "conditions": {
                "cache_buster_nonce": CACHE_BUSTER_NONCE,
                "campaign_id": campaign_id,
            },
        },
    }
    first_key = str(uuid.uuid4())
    try:
        return client.submit_results(
            campaign_id,
            results=[payload],
            idempotency_key=first_key,
            force=False,
        )
    except BoMcpOperationError as exc:
        error_code = str(exc.payload.get("error_code", ""))
        duplicates = exc.payload.get("duplicates_detected") or []
        if error_code == "E004" or duplicates:
            logger.info("Retrying duplicate suggestion submission with force=True for %s", suggestion["suggestion_id"])
            return client.submit_results(
                campaign_id,
                results=[payload],
                idempotency_key=str(uuid.uuid4()),
                force=True,
            )
        raise


def _record_attempt(
    *,
    paths: RuntimePaths,
    attempts: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    append_jsonl(paths.attempts_jsonl, record)
    attempts.append(record)
    return attempts


def _maybe_emit_heartbeat(last_heartbeat_at: float, heartbeat_s: float, attempted: int, max_attempts: int, campaign_id: str) -> float:
    now = time.time()
    if now - last_heartbeat_at >= heartbeat_s:
        _heartbeat(
            f"campaign_id={campaign_id} attempted={attempted}/{max_attempts} pid={os.getpid()}"
        )
        return now
    return last_heartbeat_at


def _maybe_stop_requested(stop_file: Path, campaign_id: str, logger: logging.Logger) -> bool:
    if stop_file.exists():
        logger.info("Stop file detected at %s", stop_file)
        _event(f"stop-file-detected campaign_id={campaign_id} stop_file={stop_file}")
        stop_file.unlink()
        return True
    return False


def _pause_if_running(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    _ensure_marker(campaign)
    status = str(campaign.get("status", ""))
    if status == "running":
        logger.info("Pausing running campaign %s", campaign_id)
        client.lifecycle(campaign_id, action="pause")
        campaign = client.get_campaign(campaign_id)
    return campaign


def _write_diagnostics(client: BoMcpClient, campaign_id: str, paths: RuntimePaths, logger: logging.Logger) -> None:
    try:
        diagnostics = client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=600.0)
        write_json(paths.diagnostics_json, diagnostics)
    except Exception as exc:  # pragma: no cover - nonfatal artifact refresh
        logger.warning("Unable to fetch diagnostics: %s", exc)


def run_campaign(config: RunConfig) -> int:
    api_url = _require_direct_arylation_api_url()
    client = BoMcpClient.from_env(timeout_s=max(float(config.poll_s), 120.0))
    campaign_id = _ensure_campaign(client, config)
    paths = _runtime_paths(config.artifact_root, campaign_id)
    paths.artifact_dir.mkdir(parents=True, exist_ok=True)
    logger = _setup_logging(paths.log_file)
    _write_runtime_config(paths, RunConfig(
        campaign_id=campaign_id,
        artifact_root=config.artifact_root,
        max_attempts=config.max_attempts,
        campaign_max_observations=config.campaign_max_observations,
        random_seed=config.random_seed,
        initial_design_size=config.initial_design_size,
        poll_s=config.poll_s,
        heartbeat_s=config.heartbeat_s,
        request_timeout_s=config.request_timeout_s,
        stop_file=config.stop_file,
    ))
    paths.campaign_id_txt.write_text(campaign_id + "\n", encoding="utf-8")

    logger.info("Starting campaign runner nonce=%s", CACHE_BUSTER_NONCE)
    logfire.info(
        "starting_direct_arylation_campaign",
        campaign_id=campaign_id,
        cache_buster_nonce=CACHE_BUSTER_NONCE,
        max_attempts=config.max_attempts,
        campaign_max_observations=config.campaign_max_observations,
    )
    campaign = _resume_if_needed(client, campaign_id, logger)
    _ensure_marker(campaign)
    _event(
        f"campaign-ready campaign_id={campaign_id} status={campaign.get('status')} max_attempts={config.max_attempts} campaign_max_observations={config.campaign_max_observations} artifact_dir={paths.artifact_dir}"
    )

    attempts = load_jsonl(paths.attempts_jsonl)
    _persist_snapshot(client=client, campaign_id=campaign_id, paths=paths, attempts=attempts, logger=logger)
    attempted = _normalize_attempt_count(attempts)
    last_heartbeat_at = 0.0
    session = requests.Session()

    try:
        while attempted < config.max_attempts:
            last_heartbeat_at = _maybe_emit_heartbeat(
                last_heartbeat_at,
                config.heartbeat_s,
                attempted,
                config.max_attempts,
                campaign_id,
            )
            if _maybe_stop_requested(config.stop_file, campaign_id, logger):
                break
            decision = client.next_action(campaign_id)
            logger.info("next_action=%s", decision)
            action = str(decision.get("action", ""))
            if action != "bo_generate_suggestions":
                _alert(
                    "bo-server-stop action="
                    f"{action} reason={decision.get('reason')} campaign_id={campaign_id} attempted={attempted}/{config.max_attempts}"
                )
                break
            suggestion = _pending_or_new_suggestion(client, campaign_id, logger)
            if suggestion is None:
                break
            candidate = canonical_candidate(dict(suggestion["parameter_values"]))
            signature = candidate_signature(candidate)
            attempt_number = attempted + 1
            logger.info("Attempt %s suggestion_id=%s candidate=%s", attempt_number, suggestion["suggestion_id"], candidate)
            _event(
                f"attempt-start campaign_id={campaign_id} attempt={attempt_number}/{config.max_attempts} suggestion_id={suggestion['suggestion_id']} candidate={candidate}"
            )
            started_at = time.time()
            try:
                evaluation = evaluate_candidate(
                    api_url=api_url,
                    candidate=candidate,
                    timeout_s=config.request_timeout_s,
                    session=session,
                )
                submission = _submit_result(
                    client,
                    campaign_id,
                    suggestion,
                    evaluation.objective_value,
                    logger,
                )
                duration_s = round(time.time() - started_at, 3)
                record = {
                    "cache_buster_nonce": CACHE_BUSTER_NONCE,
                    "attempt_number": attempt_number,
                    "campaign_id": campaign_id,
                    "suggestion_id": suggestion["suggestion_id"],
                    "candidate": candidate,
                    "candidate_signature": signature,
                    "status": "submitted",
                    "objective_name": evaluation.objective_name,
                    "objective_value": evaluation.objective_value,
                    "duration_s": duration_s,
                    "submission": submission,
                    "oracle_response": evaluation.response_payload,
                }
                attempts = _record_attempt(paths=paths, attempts=attempts, record=record)
                attempted += 1
                _result(
                    f"attempt={attempt_number}/{config.max_attempts} status=submitted campaign_id={campaign_id} suggestion_id={suggestion['suggestion_id']} yield={evaluation.objective_value:.4f} candidate={candidate}"
                )
            except EvaluationFailure as exc:
                duration_s = round(time.time() - started_at, 3)
                logger.warning("Evaluation failure for suggestion %s: %s", suggestion["suggestion_id"], exc)
                client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                record = {
                    "cache_buster_nonce": CACHE_BUSTER_NONCE,
                    "attempt_number": attempt_number,
                    "campaign_id": campaign_id,
                    "suggestion_id": suggestion["suggestion_id"],
                    "candidate": exc.candidate,
                    "candidate_signature": signature,
                    "status": "evaluation_failed",
                    "duration_s": duration_s,
                    "http_status": exc.status_code,
                    "error": exc.message,
                    "response_text": exc.response_text,
                }
                attempts = _record_attempt(paths=paths, attempts=attempts, record=record)
                attempted += 1
                _alert(
                    f"attempt={attempt_number}/{config.max_attempts} status=evaluation_failed campaign_id={campaign_id} suggestion_id={suggestion['suggestion_id']} http_status={exc.status_code} candidate={exc.candidate}"
                )
                _result(
                    f"attempt={attempt_number}/{config.max_attempts} status=evaluation_failed campaign_id={campaign_id} suggestion_id={suggestion['suggestion_id']} candidate={exc.candidate} error={exc.message}"
                )
            except (BoMcpClientError, BoMcpOperationError, requests.RequestException) as exc:
                duration_s = round(time.time() - started_at, 3)
                logger.exception("Submission or transport failure for suggestion %s", suggestion["suggestion_id"])
                record = {
                    "cache_buster_nonce": CACHE_BUSTER_NONCE,
                    "attempt_number": attempt_number,
                    "campaign_id": campaign_id,
                    "suggestion_id": suggestion["suggestion_id"],
                    "candidate": candidate,
                    "candidate_signature": signature,
                    "status": "submission_failed",
                    "duration_s": duration_s,
                    "error": str(exc),
                }
                attempts = _record_attempt(paths=paths, attempts=attempts, record=record)
                attempted += 1
                _alert(
                    f"attempt={attempt_number}/{config.max_attempts} status=submission_failed campaign_id={campaign_id} suggestion_id={suggestion['suggestion_id']} candidate={candidate}"
                )
                _result(
                    f"attempt={attempt_number}/{config.max_attempts} status=submission_failed campaign_id={campaign_id} suggestion_id={suggestion['suggestion_id']} candidate={candidate} error={exc}"
                )
            _persist_snapshot(client=client, campaign_id=campaign_id, paths=paths, attempts=attempts, logger=logger)
            if attempted < config.max_attempts:
                time.sleep(config.poll_s)
    finally:
        _persist_snapshot(client=client, campaign_id=campaign_id, paths=paths, attempts=attempts, logger=logger)
        _write_diagnostics(client, campaign_id, paths, logger)
        campaign = _pause_if_running(client, campaign_id, logger)
        write_json(paths.campaign_json, campaign)
        try:
            write_json(paths.bo_results_json, client.get_results(campaign_id))
        except Exception as exc:  # pragma: no cover - nonfatal artifact refresh
            logger.warning("Unable to refresh BO results after pause: %s", exc)
        summary = summarize_attempts(campaign_id, attempts)
        write_json(paths.summary_json, summary)
        _result(
            "campaign-summary "
            f"campaign_id={campaign_id} status={campaign.get('status')} attempted={summary['attempted_evaluations']} "
            f"successful={summary['successful_evaluations']} best_yield={summary['best_measured_yield']} "
            f"best_conditions={summary['best_conditions']} artifact_dir={paths.artifact_dir}"
        )
        _event(
            f"shutdown campaign_id={campaign_id} final_status={campaign.get('status')} artifact_dir={paths.artifact_dir}"
        )
    return 0
