import json
import logging
import threading
import time
import uuid
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient

from .artifacts import append_result, artifact_paths, configure_file_log, emit_result
from .evaluator import evaluate
from .intake import CACHE_BUSTER_NONCE, OWNERSHIP_MARKER, build_intake
from .search_space import PARAMETER_NAMES

TOTAL_ATTEMPT_BUDGET = 60
DEFAULT_BATCH_SIZE = 4


def _point_key(parameters: dict) -> tuple[float, ...]:
    return tuple(float(parameters[name]) for name in PARAMETER_NAMES)


def _heartbeat(stop: threading.Event, interval_s: int) -> None:
    while not stop.wait(interval_s):
        print("[HEARTBEAT] Ackley BO-MCP campaign is active", flush=True)


def _ensure_owned(client: BoMcpClient, campaign_id: str) -> dict:
    campaign = client.get_campaign(campaign_id)
    if OWNERSHIP_MARKER not in campaign.get("name", ""):
        raise RuntimeError(
            f"Refusing campaign {campaign_id}: name lacks ownership marker {OWNERSHIP_MARKER}"
        )
    return campaign


def _ensure_running(client: BoMcpClient, campaign_id: str) -> None:
    status = _ensure_owned(client, campaign_id).get("status")
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        print(f"[EVENT] resumed campaign_id={campaign_id}", flush=True)
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        print(f"[EVENT] reopened campaign_id={campaign_id}", flush=True)
    elif status in {"terminated", "failed"}:
        raise RuntimeError(f"Campaign {campaign_id} cannot continue from status={status}")


def _create_or_reuse(client: BoMcpClient, campaign_id: str | None) -> str:
    if campaign_id:
        _ensure_owned(client, campaign_id)
        return campaign_id
    intake = build_intake()
    client.validate_intake(intake)
    response = client.create_campaign(
        intake,
        idempotency_key=str(uuid.uuid5(uuid.NAMESPACE_URL, CACHE_BUSTER_NONCE)),
    )
    created_id = response["campaign_id"]
    _ensure_owned(client, created_id)
    replay = bool(response.get("idempotency_replay"))
    print(f"[EVENT] campaign_id={created_id} created={not replay} idempotency_replay={replay}", flush=True)
    return created_id


def _server_attempt_state(client: BoMcpClient, campaign_id: str) -> tuple[int, set, list[dict]]:
    results = client.get_results(campaign_id)
    suggestions = client.query_suggestions(campaign_id, limit=500)
    evaluated = {_point_key(row["parameter_values"]) for row in results}
    successful = len(evaluated)
    failed = 0
    for suggestion in sorted(
        suggestions, key=lambda row: (row.get("created_at", ""), row["suggestion_id"])
    ):
        if suggestion.get("status") != "rejected" or not suggestion.get("parameter_values"):
            continue
        key = _point_key(suggestion["parameter_values"])
        if key not in evaluated:
            evaluated.add(key)
            failed += 1
    pending = [row for row in suggestions if row.get("status") == "pending"]
    return successful + failed, evaluated, pending


def _row(index: int, parameters: dict, status: str, reason: str | None, raw, objective) -> dict:
    return {
        "evaluation_index": index,
        "parameter_values": {name: float(parameters[name]) for name in PARAMETER_NAMES},
        "objective_values": {"surface_response": objective},
        "status": status,
        "failure_reason": reason,
        "raw_response": raw,
    }


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    status = _ensure_owned(client, campaign_id).get("status")
    if status == "running":
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] paused campaign_id={campaign_id}", flush=True)
    else:
        print(f"[EVENT] shutdown campaign_id={campaign_id} status={status}", flush=True)


def run_campaign(
    campaign_id: str | None,
    attempt_budget: int,
    poll_s: int,
    heartbeat_s: int,
    stop_file: Path,
) -> str:
    client = BoMcpClient.from_env(timeout_s=180.0)
    campaign_id = _create_or_reuse(client, campaign_id)
    _ensure_running(client, campaign_id)
    results_path, log_path = artifact_paths(campaign_id)
    configure_file_log(log_path)
    logfire.info("Ackley campaign invocation started", campaign_id=campaign_id)
    print(f"[EVENT] results_artifact={results_path} run_log={log_path}", flush=True)

    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(heartbeat_stop, heartbeat_s), daemon=True
    )
    heartbeat.start()
    invocation_attempts = 0

    try:
        while invocation_attempts < attempt_budget:
            if stop_file.exists():
                print(f"[EVENT] stop file detected: {stop_file}", flush=True)
                stop_file.unlink()
                break

            attempted, evaluated, pending = _server_attempt_state(client, campaign_id)
            if attempted >= TOTAL_ATTEMPT_BUDGET:
                print(f"[EVENT] exact attempt budget reached: {attempted}/60", flush=True)
                break

            if not pending:
                decision = client.next_action(campaign_id)
                if decision.get("action") != "bo_generate_suggestions":
                    print(
                        f"[ALERT] server stop action={decision.get('action')} reason={decision.get('reason')}",
                        flush=True,
                    )
                    break
                batch_size = min(
                    DEFAULT_BATCH_SIZE,
                    TOTAL_ATTEMPT_BUDGET - attempted,
                    attempt_budget - invocation_attempts,
                )
                try:
                    generated = client.generate_suggestions(
                        campaign_id, batch_size=batch_size, timeout_s=900.0
                    )
                    pending = generated.get("suggestions", [])
                    print(
                        f"[EVENT] generated batch_size={len(pending)} iteration={generated.get('iteration')}",
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[ALERT] suggestion generation error: {exc}", flush=True)
                    time.sleep(poll_s)
                    pending = client.query_suggestions(
                        campaign_id, status_filter="pending", limit=500
                    )
                    if not pending:
                        break

            for suggestion in pending:
                if invocation_attempts >= attempt_budget or attempted >= TOTAL_ATTEMPT_BUDGET:
                    break
                parameters = suggestion["parameter_values"]
                suggestion_id = suggestion["suggestion_id"]
                key = _point_key(parameters)
                if key in evaluated:
                    client.update_suggestion_status(suggestion_id, "rejected")
                    print(f"[EVENT] rejected duplicate suggestion_id={suggestion_id}", flush=True)
                    continue

                index = attempted + 1
                try:
                    raw_response, surface_response = evaluate(parameters)
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    row = _row(index, parameters, "failed", reason, None, None)
                    client.update_suggestion_status(suggestion_id, "rejected")
                    append_result(results_path, row)
                    emit_result(row)
                    print(f"[ALERT] evaluation failed suggestion_id={suggestion_id}: {reason}", flush=True)
                else:
                    payload = {
                        "parameter_values": parameters,
                        "objective_values": {"surface_response": surface_response},
                        "suggestion_id": suggestion_id,
                    }
                    submit_key = str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:{suggestion_id}:result")
                    )
                    try:
                        client.submit_results(
                            campaign_id,
                            results=[payload],
                            idempotency_key=submit_key,
                        )
                    except Exception:
                        try:
                            client.submit_results(
                                campaign_id,
                                results=[payload],
                                idempotency_key=submit_key,
                            )
                        except Exception as exc:
                            reason = f"submission failed: {type(exc).__name__}: {exc}"
                            client.update_suggestion_status(suggestion_id, "rejected")
                            row = _row(
                                index,
                                parameters,
                                "submission_failed",
                                reason,
                                raw_response,
                                surface_response,
                            )
                            append_result(results_path, row)
                            emit_result(row)
                            print(f"[ALERT] {reason}", flush=True)
                        else:
                            row = _row(index, parameters, "success", None, raw_response, surface_response)
                            append_result(results_path, row)
                            emit_result(row)
                    else:
                        row = _row(index, parameters, "success", None, raw_response, surface_response)
                        append_result(results_path, row)
                        emit_result(row)

                attempted += 1
                invocation_attempts += 1
                evaluated.add(key)
                logging.info("completed evaluation_index=%s suggestion_id=%s", index, suggestion_id)

        final_attempts, _, _ = _server_attempt_state(client, campaign_id)
        print(
            f"[EVENT] invocation complete campaign_id={campaign_id} total_attempts={final_attempts}/60",
            flush=True,
        )
        return campaign_id
    finally:
        heartbeat_stop.set()
        _pause_if_running(client, campaign_id)
