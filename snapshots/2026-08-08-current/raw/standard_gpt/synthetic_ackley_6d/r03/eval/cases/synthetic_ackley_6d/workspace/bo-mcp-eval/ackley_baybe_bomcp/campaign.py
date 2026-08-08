from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient

from . import TOTAL_ATTEMPT_BUDGET
from .evaluator import evaluate_ackley
from .intake import build_campaign_intake
from .reporting import (
    append_jsonl,
    ensure_artifact_dir,
    write_json,
    write_markdown_report,
    write_rows_csv,
)
from .search_space import PARAMETER_NAMES, canonical_parameter_key, ordered_parameter_values


@dataclass(slots=True)
class CampaignConfig:
    campaign_id: str | None
    poll_s: int
    heartbeat_s: int
    stop_file: Path
    smoke_test: bool


def _emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def _configure_file_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("ackley_baybe_bomcp")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _ordered_suggestions(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        suggestions,
        key=lambda item: (
            item.get("created_at", ""),
            item.get("suggestion_id", ""),
        ),
    )


def _rebuild_rows(
    suggestions: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_by_suggestion = {
        row.get("suggestion_id"): row for row in results if row.get("suggestion_id")
    }
    rows: list[dict[str, Any]] = []
    for suggestion in _ordered_suggestions(suggestions):
        suggestion_id = suggestion.get("suggestion_id")
        parameter_values = suggestion.get("parameter_values") or {}
        status = suggestion.get("status")
        if suggestion_id in result_by_suggestion:
            evaluation = evaluate_ackley(parameter_values)
            rows.append(
                {
                    "evaluation_index": len(rows) + 1,
                    "parameter_values": evaluation["parameter_values"],
                    "objective_values": evaluation["objective_values"],
                    "status": "completed",
                    "failure_reason": "",
                    "raw_response": evaluation["raw_response"],
                    "suggestion_id": suggestion_id,
                }
            )
        elif status == "rejected":
            rows.append(
                {
                    "evaluation_index": len(rows) + 1,
                    "parameter_values": ordered_parameter_values(parameter_values),
                    "objective_values": {},
                    "status": "failed",
                    "failure_reason": "rejected_suggestion",
                    "raw_response": None,
                    "suggestion_id": suggestion_id,
                }
            )
    return rows


def _load_server_state(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    suggestions = client.query_suggestions(campaign_id, status_filter=None, limit=500)
    results = client.get_results(campaign_id)
    rows = _rebuild_rows(suggestions, results)
    attempted_keys = {
        canonical_parameter_key(row["parameter_values"])
        for row in rows
        if row.get("parameter_values")
    }
    pending = [item for item in _ordered_suggestions(suggestions) if item.get("status") == "pending"]
    return {
        "suggestions": suggestions,
        "results": results,
        "rows": rows,
        "attempted_keys": attempted_keys,
        "pending": pending,
    }


def _build_summary(campaign_id: str, rows: list[dict[str, Any]], artifact_dir: Path) -> dict[str, Any]:
    successful_rows = [row for row in rows if row.get("status") == "completed"]
    best_row = None
    if successful_rows:
        best_row = max(
            successful_rows,
            key=lambda row: row["objective_values"]["surface_response"],
        )
    return {
        "campaign_id": campaign_id,
        "attempted_evaluations": len(rows),
        "successful_evaluations": len(successful_rows),
        "best_parameter_values": best_row["parameter_values"] if best_row else None,
        "best_raw_response": best_row["raw_response"] if best_row else None,
        "best_surface_response": (
            best_row["objective_values"]["surface_response"] if best_row else None
        ),
        "artifact_dir": str(artifact_dir),
        "results_csv": str(artifact_dir / "evaluated_candidates.csv"),
        "results_json": str(artifact_dir / "evaluated_candidates.json"),
        "report_path": str(artifact_dir / "final_report.md"),
        "run_log": str(artifact_dir / "run.log"),
    }


def _persist_snapshot(campaign_id: str, artifact_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _build_summary(campaign_id, rows, artifact_dir)
    write_json(artifact_dir / "evaluated_candidates.json", rows)
    write_rows_csv(artifact_dir / "evaluated_candidates.csv", rows)
    write_json(artifact_dir / "summary.json", summary)
    write_markdown_report(artifact_dir / "final_report.md", summary, rows)
    return summary


def _ensure_running_campaign(client: BoMcpClient, campaign_id: str) -> None:
    status = client.next_action(campaign_id).get("status", "")
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        _emit("EVENT", f"Resumed paused campaign {campaign_id}.")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        _emit("EVENT", f"Reopened completed campaign {campaign_id}.")


def _pause_campaign(client: BoMcpClient, campaign_id: str) -> None:
    status = client.next_action(campaign_id).get("status", "")
    if status not in {"paused", "completed", "terminated"}:
        client.lifecycle(campaign_id, action="pause")
        _emit("EVENT", f"Paused campaign {campaign_id}.")


def _expire_duplicate_suggestion(
    client: BoMcpClient,
    suggestion: dict[str, Any],
    attempted_keys: set[tuple[str, ...]],
    logger: logging.Logger,
) -> bool:
    parameter_values = suggestion.get("parameter_values") or {}
    suggestion_id = suggestion.get("suggestion_id", "unknown")
    parameter_key = canonical_parameter_key(parameter_values)
    if parameter_key not in attempted_keys:
        return False
    client.update_suggestion_status(suggestion_id, "expired")
    logger.info("Expired duplicate suggestion %s", suggestion_id)
    _emit("EVENT", f"Expired duplicate suggestion {suggestion_id} before evaluation.")
    return True


def _select_suggestion(
    client: BoMcpClient,
    campaign_id: str,
    attempted_keys: set[tuple[str, ...]],
    poll_s: int,
    logger: logging.Logger,
) -> dict[str, Any] | None:
    state = _load_server_state(client, campaign_id)
    for suggestion in state["pending"]:
        if not _expire_duplicate_suggestion(client, suggestion, attempted_keys, logger):
            return suggestion

    decision = client.next_action(campaign_id)
    if decision.get("action") != "bo_generate_suggestions":
        _emit(
            "ALERT",
            "BO-MCP declined further suggestion generation before the 60-attempt budget was reached. "
            f"status={decision.get('status')} action={decision.get('action')} reason={decision.get('reason')}",
        )
        logger.warning("Suggestion generation stopped early: %s", decision)
        return None

    _emit("EVENT", f"Generating one new suggestion for campaign {campaign_id}.")
    generated = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=float(poll_s))
    suggestions = generated.get("suggestions") or []
    if not suggestions:
        _emit("ALERT", "BO-MCP returned no suggestions.")
        logger.warning("No suggestions returned for campaign %s", campaign_id)
        return None
    suggestion = suggestions[0]
    if _expire_duplicate_suggestion(client, suggestion, attempted_keys, logger):
        return _select_suggestion(client, campaign_id, attempted_keys, poll_s, logger)
    return suggestion


def _create_or_resume_campaign(client: BoMcpClient, config: CampaignConfig) -> tuple[str, dict[str, Any]]:
    intake = build_campaign_intake()
    if config.campaign_id:
        _emit("EVENT", f"Using existing campaign {config.campaign_id}.")
        _ensure_running_campaign(client, config.campaign_id)
        return config.campaign_id, intake

    _emit("EVENT", "Validating Ackley benchmark intake against BO-MCP.")
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"Campaign intake validation failed: {validation}")

    _emit("EVENT", "Creating BO-MCP campaign with the BayBE backend.")
    create_response = client.create_campaign(
        intake,
        idempotency_key=intake["name"],
    )
    campaign_id = create_response.get("campaign_id")
    if not campaign_id:
        raise RuntimeError(f"Campaign creation returned no campaign_id: {create_response}")
    _emit("EVENT", f"Created campaign {campaign_id}.")
    return campaign_id, intake


def run_campaign(config: CampaignConfig) -> int:
    client = BoMcpClient.from_env(timeout_s=float(max(60, config.poll_s)))
    intake = build_campaign_intake()

    if config.smoke_test:
        _emit("EVENT", "Running BO-MCP smoke test without objective evaluations.")
        validation = client.validate_intake(intake)
        if not validation.get("valid"):
            raise RuntimeError(f"Smoke-test validation failed: {validation}")
        _emit(
            "RESULT",
            "Smoke test passed: BO-MCP accepted the BayBE Ackley intake and consumed 0 objective evaluations.",
        )
        return 0

    campaign_id, intake = _create_or_resume_campaign(client, config)
    artifact_dir = ensure_artifact_dir(campaign_id)
    logger = _configure_file_logger(artifact_dir / "run.log")
    write_json(artifact_dir / "campaign_intake.json", intake)
    logger.info("Starting campaign run for %s", campaign_id)
    logfire.info("Starting Ackley BO-MCP campaign run", campaign_id=campaign_id)

    rows_jsonl_path = artifact_dir / "evaluation_events.jsonl"
    last_heartbeat = 0.0

    while True:
        state = _load_server_state(client, campaign_id)
        attempted = len(state["rows"])
        summary = _persist_snapshot(campaign_id, artifact_dir, state["rows"])

        if attempted >= TOTAL_ATTEMPT_BUDGET:
            _emit("EVENT", f"Reached the exact attempted-evaluation budget of {TOTAL_ATTEMPT_BUDGET}.")
            break

        now = time.time()
        if last_heartbeat == 0.0 or now - last_heartbeat >= config.heartbeat_s:
            _emit(
                "HEARTBEAT",
                f"campaign_id={campaign_id} attempted={summary['attempted_evaluations']} successful={summary['successful_evaluations']}",
            )
            last_heartbeat = now

        if config.stop_file.exists():
            config.stop_file.unlink()
            _emit("EVENT", f"Detected stop file {config.stop_file}; pausing after a clean checkpoint.")
            break

        suggestion = _select_suggestion(
            client,
            campaign_id,
            state["attempted_keys"],
            config.poll_s,
            logger,
        )
        if suggestion is None:
            break

        suggestion_id = suggestion.get("suggestion_id", "")
        parameter_values = ordered_parameter_values(suggestion.get("parameter_values") or {})
        evaluation_index = attempted + 1
        logger.info("Evaluating suggestion %s as attempt %s", suggestion_id, evaluation_index)
        logfire.debug(
            "Evaluating Ackley suggestion",
            campaign_id=campaign_id,
            suggestion_id=suggestion_id,
            evaluation_index=evaluation_index,
        )
        _emit("EVENT", f"Evaluating suggestion {suggestion_id} as attempt {evaluation_index}.")

        try:
            evaluation = evaluate_ackley(parameter_values)
        except Exception as exc:  # pragma: no cover - defensive failure path
            client.update_suggestion_status(suggestion_id, "rejected")
            failure_row = {
                "evaluation_index": evaluation_index,
                "parameter_values": parameter_values,
                "objective_values": {},
                "status": "failed",
                "failure_reason": str(exc),
                "raw_response": None,
                "suggestion_id": suggestion_id,
            }
            append_jsonl(rows_jsonl_path, failure_row)
            logger.exception("Evaluation failed for suggestion %s", suggestion_id)
            logfire.info(
                "Ackley evaluation failed",
                campaign_id=campaign_id,
                suggestion_id=suggestion_id,
                error=str(exc),
            )
            _emit("ALERT", f"Evaluation failed for suggestion {suggestion_id}: {exc}")
            continue

        submit_payload = {
            "suggestion_id": suggestion_id,
            "parameter_values": evaluation["parameter_values"],
            "objective_values": evaluation["objective_values"],
            "metadata": {
                "experiment_id": f"ackley-attempt-{evaluation_index}",
                "notes": "Deterministic local Ackley synthetic benchmark evaluation.",
                "conditions": {
                    "benchmark": "ackley-6d",
                    "raw_response": evaluation["raw_response"],
                },
            },
        }
        client.submit_results(
            campaign_id,
            results=[submit_payload],
            idempotency_key=f"submit-{suggestion_id}",
        )

        result_row = {
            "evaluation_index": evaluation_index,
            "parameter_values": evaluation["parameter_values"],
            "objective_values": evaluation["objective_values"],
            "status": "completed",
            "failure_reason": "",
            "raw_response": evaluation["raw_response"],
            "suggestion_id": suggestion_id,
        }
        append_jsonl(rows_jsonl_path, result_row)
        logger.info(
            "Completed attempt %s for suggestion %s with surface_response=%.8f",
            evaluation_index,
            suggestion_id,
            evaluation["objective_values"]["surface_response"],
        )
        logfire.info(
            "Ackley evaluation submitted",
            campaign_id=campaign_id,
            suggestion_id=suggestion_id,
            evaluation_index=evaluation_index,
            surface_response=evaluation["objective_values"]["surface_response"],
        )
        _emit(
            "RESULT",
            "attempt={attempt} suggestion_id={suggestion_id} status=completed surface_response={surface:.8f} raw_response={raw:.8f} "
            "x_1={x_1:.6f} x_2={x_2:.6f} x_3={x_3:.6f} x_4={x_4:.6f} x_5={x_5:.6f} x_6={x_6:.6f}".format(
                attempt=evaluation_index,
                suggestion_id=suggestion_id,
                surface=evaluation["objective_values"]["surface_response"],
                raw=evaluation["raw_response"],
                **{name: evaluation["parameter_values"][name] for name in PARAMETER_NAMES},
            ),
        )

    final_state = _load_server_state(client, campaign_id)
    final_summary = _persist_snapshot(campaign_id, artifact_dir, final_state["rows"])
    _pause_campaign(client, campaign_id)
    logger.info("Finished campaign invocation for %s", campaign_id)
    logfire.info("Ackley BO-MCP campaign invocation finished", campaign_id=campaign_id)

    _emit(
        "RESULT",
        "best_surface_response={surface} best_raw_response={raw} attempted={attempted} successful={successful} artifact_dir={artifact_dir}".format(
            surface=final_summary["best_surface_response"],
            raw=final_summary["best_raw_response"],
            attempted=final_summary["attempted_evaluations"],
            successful=final_summary["successful_evaluations"],
            artifact_dir=final_summary["artifact_dir"],
        ),
    )
    _emit(
        "RESULT",
        f"best_parameter_values={final_summary['best_parameter_values']} results_csv={final_summary['results_csv']} report={final_summary['report_path']}",
    )
    return 0
