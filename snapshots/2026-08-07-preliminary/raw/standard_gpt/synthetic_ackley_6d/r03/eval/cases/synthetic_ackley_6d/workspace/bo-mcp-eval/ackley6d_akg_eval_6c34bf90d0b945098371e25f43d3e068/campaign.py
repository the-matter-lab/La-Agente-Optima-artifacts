from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate_ackley, parameter_key
from .reporting import (
    CAMPAIGN_EXPORT_CSV,
    DIAGNOSTICS_JSON,
    RESULTS_JSONL,
    RUN_LOG,
    SUMMARY_JSON,
    append_jsonl,
    ensure_artifact_dir,
    format_parameter_values,
    load_jsonl,
    summarize_records,
    write_summary,
)
from .search_space import (
    CACHE_BUSTER_NONCE,
    CAMPAIGN_MARKER,
    OBJECTIVE_NAME,
    PARAMETER_NAMES,
    TOTAL_BUDGET,
    build_campaign_name,
    build_intake,
)


@dataclass
class RunConfig:
    artifact_root: Path
    stop_file: Path
    campaign_id: str | None = None
    campaign_label: str = "main"
    total_budget: int = TOTAL_BUDGET
    max_attempts_this_run: int | None = None
    poll_s: int = 180
    heartbeat_s: int = 1800
    random_seed: int = 271828


def _emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def _setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"ackley_campaign_{log_path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _extract_campaign_name(campaign_info: dict[str, Any]) -> str:
    direct_name = campaign_info.get("name")
    if isinstance(direct_name, str):
        return direct_name
    nested = campaign_info.get("campaign")
    if isinstance(nested, dict) and isinstance(nested.get("name"), str):
        return nested["name"]
    return json.dumps(campaign_info, sort_keys=True)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _maybe_resume_campaign(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any]:
    decision = client.next_action(campaign_id)
    status = _normalize_status(decision.get("status"))
    logger.info("Initial next_action=%s", decision)
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        _emit("EVENT", f"Resumed paused campaign {campaign_id}.")
        logger.info("Resumed paused campaign %s", campaign_id)
        decision = client.next_action(campaign_id)
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        _emit("EVENT", f"Reopened completed campaign {campaign_id}.")
        logger.info("Reopened completed campaign %s", campaign_id)
        decision = client.next_action(campaign_id)
    return decision


def _pause_if_running(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> None:
    try:
        decision = client.next_action(campaign_id)
    except Exception as exc:  # pragma: no cover - best effort shutdown
        logger.warning("Unable to query next_action during shutdown: %s", exc)
        return
    status = _normalize_status(decision.get("status"))
    if status in {"completed", "terminated", "paused"}:
        logger.info("Skipping pause because campaign status is %s", status)
        return
    client.lifecycle(campaign_id, action="pause")
    logger.info("Paused campaign %s", campaign_id)
    _emit("EVENT", f"Paused campaign {campaign_id}.")


def _create_or_attach_campaign(client: BoMcpClient, config: RunConfig, logger: logging.Logger) -> str:
    if config.campaign_id:
        campaign_info = client.get_campaign(config.campaign_id)
        campaign_name = _extract_campaign_name(campaign_info)
        if CAMPAIGN_MARKER not in campaign_name:
            raise ValueError(
                f"Campaign {config.campaign_id} is missing required marker {CAMPAIGN_MARKER}."
            )
        _emit("EVENT", f"Attached to existing campaign {config.campaign_id}.")
        logger.info("Attached to existing campaign %s", config.campaign_id)
        return config.campaign_id

    campaign_name = build_campaign_name(config.campaign_label)
    intake = build_intake(campaign_name, random_seed=config.random_seed)
    validation = client.validate_intake(intake)
    logger.info("Validation response: %s", validation)
    if not validation.get("valid", validation.get("success", False)):
        raise RuntimeError(f"Campaign intake validation failed: {validation}")
    response = client.create_campaign(
        intake,
        idempotency_key=client.make_idempotency_key(
            "create", campaign_name, CACHE_BUSTER_NONCE
        ),
    )
    if not response.get("success", False):
        raise RuntimeError(f"Campaign creation failed: {response}")
    campaign_id = str(response["campaign_id"])
    _emit("EVENT", f"Created campaign {campaign_id} ({campaign_name}).")
    logger.info("Created campaign %s with response %s", campaign_id, response)
    return campaign_id


def run_campaign(config: RunConfig) -> dict[str, Any]:
    artifact_dir = ensure_artifact_dir(config.artifact_root)
    logger = _setup_logger(artifact_dir / RUN_LOG)
    logfire.info(
        "Starting Ackley benchmark campaign run",
        marker=CAMPAIGN_MARKER,
        artifact_dir=str(artifact_dir),
    )
    client = BoMcpClient.from_env(timeout_s=max(float(config.poll_s), 120.0))
    campaign_id = _create_or_attach_campaign(client, config, logger)
    campaign_info = client.get_campaign(campaign_id)
    campaign_name = _extract_campaign_name(campaign_info)
    if CAMPAIGN_MARKER not in campaign_name:
        raise ValueError(f"Campaign {campaign_id} missing required marker.")

    prior_records = load_jsonl(artifact_dir / RESULTS_JSONL)
    next_index = len(prior_records) + 1
    decision = _maybe_resume_campaign(client, campaign_id, logger)

    existing_results = client.get_results(campaign_id)
    seen_points = {
        parameter_key(result.get("parameter_values", {}))
        for result in existing_results
        if isinstance(result, dict)
    }
    logger.info("Loaded %d server result rows", len(existing_results))

    attempts_this_run = 0
    last_heartbeat = time.monotonic()
    max_attempts_this_run = config.max_attempts_this_run or 10**9

    while attempts_this_run < max_attempts_this_run:
        if config.stop_file.exists():
            config.stop_file.unlink()
            _emit("EVENT", f"Stop file detected at {config.stop_file}; exiting cleanly.")
            logger.info("Stop file detected, ending invocation")
            break

        now = time.monotonic()
        if now - last_heartbeat >= config.heartbeat_s:
            _emit(
                "HEARTBEAT",
                f"campaign_id={campaign_id} attempts_this_run={attempts_this_run} server_results={decision.get('n_results')}",
            )
            last_heartbeat = now

        server_results = int(decision.get("n_results") or 0)
        if server_results >= config.total_budget:
            _emit("EVENT", f"Budget reached at {server_results} submitted evaluations.")
            logger.info("Budget reached from server state")
            break

        if decision.get("action") != "bo_generate_suggestions":
            _emit(
                "EVENT",
                "Server requested stop: "
                f"action={decision.get('action')} reason={decision.get('reason')}.",
            )
            logger.info("Stopping on next_action response %s", decision)
            break

        suggestion_response = client.generate_suggestions(campaign_id, batch_size=1)
        logger.info("Suggestion response: %s", suggestion_response)
        if not suggestion_response.get("success", False):
            _emit("ALERT", f"Suggestion generation failed: {suggestion_response.get('errors')}")
            break
        suggestions = suggestion_response.get("suggestions") or []
        if not suggestions:
            _emit("ALERT", "Suggestion generation returned no suggestions.")
            break

        suggestion = suggestions[0]
        parameter_values = suggestion["parameter_values"]
        point_key = parameter_key(parameter_values)
        suggestion_id = suggestion["suggestion_id"]

        if point_key in seen_points:
            client.update_suggestion_status(suggestion_id, "rejected")
            logger.info("Rejected duplicate suggestion %s at %s", suggestion_id, parameter_values)
            _emit(
                "ALERT",
                f"Rejected duplicate suggestion {suggestion_id} for {format_parameter_values(parameter_values)}.",
            )
            decision = client.next_action(campaign_id)
            continue

        evaluation_index = next_index
        next_index += 1
        attempts_this_run += 1
        record: dict[str, Any] = {
            "evaluation_index": evaluation_index,
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "suggestion_id": suggestion_id,
            "parameter_values": {name: float(parameter_values[name]) for name in PARAMETER_NAMES},
            "objective_values": {OBJECTIVE_NAME: None},
            "status": "failed",
            "failure_reason": None,
            "raw_response": None,
        }

        try:
            evaluation = evaluate_ackley(parameter_values)
            record["objective_values"] = {OBJECTIVE_NAME: float(evaluation[OBJECTIVE_NAME])}
            record["raw_response"] = float(evaluation["raw_response"])
            submit_response = client.submit_results(
                campaign_id,
                results=[
                    {
                        "suggestion_id": suggestion_id,
                        "parameter_values": record["parameter_values"],
                        "objective_values": record["objective_values"],
                        "metadata": {
                            "experiment_id": f"ackley-eval-{evaluation_index:03d}",
                            "notes": "Deterministic synthetic Ackley benchmark evaluation.",
                        },
                    }
                ],
                idempotency_key=client.make_idempotency_key(
                    "submit", campaign_id, str(evaluation_index)
                ),
            )
            logger.info("Submit response: %s", submit_response)
            if not submit_response.get("success", False):
                record["status"] = "submission_failed"
                record["failure_reason"] = "; ".join(submit_response.get("errors") or ["unknown submission failure"])
                client.update_suggestion_status(suggestion_id, "rejected")
                _emit(
                    "ALERT",
                    f"Submission failed for evaluation {evaluation_index}: {record['failure_reason']}",
                )
            else:
                record["status"] = "submitted"
                seen_points.add(point_key)
                _emit(
                    "RESULT",
                    f"evaluation_index={evaluation_index} status=submitted surface_response={record['objective_values'][OBJECTIVE_NAME]:.8f} raw_response={record['raw_response']:.8f} {format_parameter_values(record['parameter_values'])}",
                )
        except Exception as exc:  # pragma: no cover - exercised only on unexpected errors
            record["failure_reason"] = str(exc)
            client.update_suggestion_status(suggestion_id, "rejected")
            logger.exception("Evaluation failed for suggestion %s", suggestion_id)
            _emit(
                "ALERT",
                f"Evaluation failed for index {evaluation_index}: {record['failure_reason']}",
            )

        append_jsonl(artifact_dir / RESULTS_JSONL, record)
        decision = client.next_action(campaign_id)
        logger.info("Post-submit next_action: %s", decision)

    try:
        diagnostics = client.get_diagnostics(campaign_id, timeout_s=max(float(config.poll_s) * 4.0, 300.0))
        with (artifact_dir / DIAGNOSTICS_JSON).open("w", encoding="utf-8") as handle:
            json.dump(diagnostics, handle, indent=2, sort_keys=True)
            handle.write("\n")
        logger.info("Saved diagnostics")
    except Exception as exc:  # pragma: no cover - best effort reporting
        logger.warning("Diagnostics fetch failed: %s", exc)

    try:
        export_bytes, _ = client.export_campaign(campaign_id, fmt="csv")
        (artifact_dir / CAMPAIGN_EXPORT_CSV).write_bytes(export_bytes)
        logger.info("Saved campaign export")
    except Exception as exc:  # pragma: no cover - best effort reporting
        logger.warning("Campaign export failed: %s", exc)

    records = load_jsonl(artifact_dir / RESULTS_JSONL)
    summary = summarize_records(records)
    summary["campaign_id"] = campaign_id
    summary["campaign_name"] = campaign_name
    write_summary(artifact_dir / SUMMARY_JSON, summary)
    logger.info("Summary: %s", summary)

    _pause_if_running(client, campaign_id, logger)
    _emit(
        "EVENT",
        f"Run complete for campaign_id={campaign_id} attempted={summary['attempted_evaluations']} successful={summary['successful_evaluations']}.",
    )
    return summary
