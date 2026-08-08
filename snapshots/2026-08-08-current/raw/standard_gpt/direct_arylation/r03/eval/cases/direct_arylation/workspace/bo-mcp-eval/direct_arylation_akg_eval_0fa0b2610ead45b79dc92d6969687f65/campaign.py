from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient

from .evaluate import evaluate_candidate
from .intake import build_intake
from .reporting import append_jsonl, build_summary, utc_now_iso, write_json
from .search_space import (
    CAMPAIGN_NAME,
    CHAT_TRACE_ID,
    DEFAULT_ARTIFACT_DIR,
    MARKER,
    NONCE,
    OBJECTIVE_NAME,
    TOTAL_ATTEMPT_BUDGET,
    ordered_parameter_values,
)


@dataclass
class RunConfig:
    campaign_id: str | None = None
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    max_new_attempts: int = TOTAL_ATTEMPT_BUDGET
    total_attempt_budget: int = TOTAL_ATTEMPT_BUDGET
    poll_s: int = 180
    heartbeat_s: int = 1800
    stop_file: Path = Path("STOP")
    oracle_timeout_s: float = 60.0


def emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def format_candidate(parameter_values: dict[str, Any]) -> str:
    values = ordered_parameter_values(parameter_values)
    return (
        f"base={values['base']}; ligand={values['ligand']}; solvent={values['solvent']}; "
        f"concentration={values['concentration']}; temperature_c={values['temperature_c']}"
    )


def make_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger(f"direct_arylation.{log_path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def fetch_state(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    results = client.get_results(campaign_id)
    suggestions = client.query_suggestions(campaign_id, status_filter=None, limit=500)
    rejected = [item for item in suggestions if item.get("status") == "rejected"]
    pending = [item for item in suggestions if item.get("status") == "pending"]
    return {
        "results": results,
        "suggestions": suggestions,
        "pending": pending,
        "attempted_total": len(results) + len(rejected),
        "successful_total": len(results),
        "failed_total": len(rejected),
    }


def ensure_campaign(client: BoMcpClient, requested_campaign_id: str | None, logger: logging.Logger) -> str:
    if requested_campaign_id:
        campaign = client.get_campaign(requested_campaign_id)
        if MARKER not in campaign["name"]:
            raise RuntimeError(f"Campaign {requested_campaign_id} does not contain required marker {MARKER}.")
        status = campaign["status"]
        logger.info("Using existing campaign %s with status %s", requested_campaign_id, status)
        if status == "paused":
            client.lifecycle(requested_campaign_id, action="resume")
        elif status == "completed":
            client.lifecycle(requested_campaign_id, action="reopen")
        return requested_campaign_id

    intake = build_intake()
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"Campaign intake validation failed: {validation}")
    create_response = client.create_campaign(
        intake,
        idempotency_key=BoMcpClient.make_idempotency_key(CAMPAIGN_NAME, NONCE, uuid.uuid4().hex),
    )
    campaign_id = create_response["campaign_id"]
    logger.info("Created campaign %s", campaign_id)
    return campaign_id


def choose_suggestion(client: BoMcpClient, campaign_id: str, state: dict[str, Any], logger: logging.Logger, poll_s: int) -> dict[str, Any] | None:
    if state["pending"]:
        suggestion = sorted(
            state["pending"],
            key=lambda item: (item.get("iteration") or 0, item.get("created_at") or "", item["suggestion_id"]),
        )[0]
        logger.info("Reusing pending suggestion %s", suggestion["suggestion_id"])
        return suggestion

    decision = client.next_action(campaign_id)
    action = decision.get("action")
    logger.info("next_action=%s payload=%s", action, decision)
    if action != "bo_generate_suggestions":
        reason = decision.get("reason") or decision.get("message") or "no further suggestions requested"
        emit("EVENT", f"Server action is {action}; {reason}. Waiting {poll_s}s before shutdown.")
        if poll_s > 0:
            time.sleep(poll_s)
        return None

    try:
        response = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=max(120.0, float(poll_s)))
        suggestions = response.get("suggestions", [])
        if suggestions:
            return suggestions[0]
    except Exception as exc:  # pragma: no cover - defensive recovery path
        logger.warning("Suggestion generation raised %s; checking for pending suggestions", exc)
        pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
        if pending:
            return pending[0]
        raise

    return None


def record_attempt(attempts_path: Path, campaign_id: str, suggestion_id: str, attempt_number: int, evaluation: dict[str, Any]) -> None:
    payload = {
        "record_type": "attempt",
        "recorded_at": utc_now_iso(),
        "chat_trace_id": CHAT_TRACE_ID,
        "marker": MARKER,
        "nonce": NONCE,
        "campaign_id": campaign_id,
        "suggestion_id": suggestion_id,
        "attempt_number": attempt_number,
        "status": evaluation["status"],
        "parameter_values": ordered_parameter_values(evaluation["parameter_values"]),
    }
    if evaluation["status"] == "successful":
        payload["objective_values"] = {OBJECTIVE_NAME: float(evaluation["objective_values"][OBJECTIVE_NAME])}
    if "http_status" in evaluation:
        payload["http_status"] = evaluation["http_status"]
    if "error" in evaluation:
        payload["error"] = evaluation["error"]
    payload["oracle_url"] = evaluation.get("oracle_url")
    append_jsonl(attempts_path, payload)


def pause_if_running(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    if campaign["status"] == "running":
        logger.info("Pausing running campaign %s", campaign_id)
        client.lifecycle(campaign_id, action="pause")
        campaign = client.get_campaign(campaign_id)
    return campaign


def refresh_summary(client: BoMcpClient, campaign_id: str, summary_path: Path) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    results = client.get_results(campaign_id)
    suggestions = client.query_suggestions(campaign_id, status_filter=None, limit=500)
    summary = build_summary(campaign, results, suggestions)
    write_json(summary_path, summary)
    return summary


def run_campaign(config: RunConfig) -> dict[str, Any]:
    if config.max_new_attempts < 1:
        raise ValueError("max_new_attempts must be at least 1")
    if config.total_attempt_budget != TOTAL_ATTEMPT_BUDGET:
        raise ValueError(f"total_attempt_budget must remain fixed at {TOTAL_ATTEMPT_BUDGET}")
    if not os.environ.get("BO_MCP_API_URL") or not os.environ.get("BO_MCP_API_KEY"):
        raise RuntimeError("BO_MCP_API_URL and BO_MCP_API_KEY are required.")
    if not os.environ.get("DIRECT_ARYLATION_API_URL"):
        raise RuntimeError("DIRECT_ARYLATION_API_URL is required.")

    artifact_dir = Path(config.artifact_dir)
    attempts_path = artifact_dir / "attempts.jsonl"
    summary_path = artifact_dir / "summary.json"
    log_path = artifact_dir / "run.log"
    logger = make_logger(log_path)
    client = BoMcpClient.from_env()
    campaign_id = ensure_campaign(client, config.campaign_id, logger)

    emit("EVENT", f"Campaign ready: id={campaign_id}; marker={MARKER}; trace={CHAT_TRACE_ID}")
    emit("EVENT", f"Artifacts: {artifact_dir}")

    invocation_attempts = 0
    started = time.monotonic()
    last_heartbeat = started

    while invocation_attempts < config.max_new_attempts:
        now = time.monotonic()
        if now - last_heartbeat >= config.heartbeat_s:
            emit(
                "HEARTBEAT",
                f"campaign_id={campaign_id}; new_attempts={invocation_attempts}/{config.max_new_attempts}; elapsed_s={int(now - started)}",
            )
            last_heartbeat = now

        if config.stop_file.exists():
            emit("EVENT", f"Stop file detected at {config.stop_file}; deleting marker and shutting down cleanly.")
            config.stop_file.unlink()
            break

        state = fetch_state(client, campaign_id)
        if state["attempted_total"] >= config.total_attempt_budget:
            emit("ALERT", f"Attempt budget reached: {state['attempted_total']}/{config.total_attempt_budget}.")
            break

        suggestion = choose_suggestion(client, campaign_id, state, logger, config.poll_s)
        if suggestion is None:
            break

        suggestion_id = suggestion["suggestion_id"]
        parameter_values = ordered_parameter_values(suggestion["parameter_values"])
        attempt_number = state["attempted_total"] + 1
        logger.info("Evaluating suggestion %s with %s", suggestion_id, parameter_values)
        evaluation = evaluate_candidate(parameter_values, timeout_s=config.oracle_timeout_s)
        invocation_attempts += 1

        if evaluation["status"] == "successful":
            client.submit_results(
                campaign_id,
                results=[
                    {
                        "suggestion_id": suggestion_id,
                        "parameter_values": parameter_values,
                        "objective_values": {OBJECTIVE_NAME: float(evaluation["objective_values"][OBJECTIVE_NAME])},
                    }
                ],
                idempotency_key=BoMcpClient.make_idempotency_key("submit-result", campaign_id, suggestion_id),
                force=True,
            )
            emit(
                "RESULT",
                f"attempt={attempt_number}/{config.total_attempt_budget}; status=successful; yield={evaluation['objective_values'][OBJECTIVE_NAME]:.6g}; {format_candidate(parameter_values)}",
            )
        else:
            client.update_suggestion_status(suggestion_id, "rejected")
            emit(
                "ALERT",
                f"attempt={attempt_number}/{config.total_attempt_budget}; status=failed; suggestion_id={suggestion_id}; error={evaluation.get('error', 'unknown error')}",
            )
            emit(
                "RESULT",
                f"attempt={attempt_number}/{config.total_attempt_budget}; status=failed; {format_candidate(parameter_values)}",
            )

        record_attempt(attempts_path, campaign_id, suggestion_id, attempt_number, evaluation)
        summary = refresh_summary(client, campaign_id, summary_path)
        logger.info("Updated summary: %s", summary)

    final_campaign = pause_if_running(client, campaign_id, logger)
    final_summary = refresh_summary(client, campaign_id, summary_path)
    best = final_summary.get("best")
    if best:
        emit(
            "RESULT",
            f"best_yield={best['objective_values'][OBJECTIVE_NAME]:.6g}; {format_candidate(best['parameter_values'])}",
        )
    emit(
        "EVENT",
        f"Invocation complete: campaign_id={campaign_id}; status={final_campaign['status']}; attempted={final_summary['attempted_evaluations']}/{config.total_attempt_budget}; successes={final_summary['successful_evaluations']}; failures={final_summary['failed_evaluations']}",
    )
    emit("EVENT", f"Summary written to {summary_path}")
    return final_summary
