import json
import logging
import threading
import time
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError

from .evaluator import EvaluationFailure, evaluate
from .intake import CACHE_BUSTER, OWNERSHIP_MARKER, build_intake
from .reporting import append_attempt, collect_attempts, write_final_report
from .search_space import normalize_candidate

TOTAL_ATTEMPT_BUDGET = 60


def _heartbeat(stop: threading.Event, interval_s: float, campaign_id: str) -> None:
    while not stop.wait(interval_s):
        print(f"[HEARTBEAT] campaign_id={campaign_id} running", flush=True)


def _activate(client: BoMcpClient, campaign_id: str) -> None:
    campaign = client.get_campaign(campaign_id)
    if OWNERSHIP_MARKER not in campaign["name"]:
        raise RuntimeError("Refusing campaign without the required ownership marker")
    status = campaign["status"].lower()
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
    elif status not in {"created", "running"}:
        raise RuntimeError(f"Campaign cannot be resumed from status {status!r}")


def _campaign(client: BoMcpClient, campaign_id: str | None) -> str:
    if campaign_id:
        _activate(client, campaign_id)
        return campaign_id
    intake = build_intake()
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"BO-MCP rejected intake: {validation.get('errors')}")
    create_key = str(uuid5(NAMESPACE_URL, f"{OWNERSHIP_MARKER}:{CACHE_BUSTER}:create"))
    created = client.create_campaign(intake, idempotency_key=create_key)
    campaign_id = created["campaign_id"]
    _activate(client, campaign_id)
    return campaign_id


def _next_suggestion(client: BoMcpClient, campaign_id: str, poll_s: float) -> dict | None:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
    if pending:
        return pending[0]
    decision = client.next_action(campaign_id)
    action = decision.get("action")
    if action in {"wait", "retry", "poll"}:
        print(f"[EVENT] BO-MCP requested {action}; polling in {poll_s:g}s", flush=True)
        time.sleep(poll_s)
        return None
    if action != "bo_generate_suggestions":
        print(f"[ALERT] BO-MCP stop condition action={action!r}", flush=True)
        return None
    try:
        generated = client.generate_suggestions(campaign_id, batch_size=1)
        return generated["suggestions"][0]
    except BoMcpClientError:
        pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
        if pending:
            print("[EVENT] recovered a pending suggestion after generation error", flush=True)
            return pending[0]
        raise


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    if client.get_campaign(campaign_id)["status"].lower() == "running":
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] campaign paused campaign_id={campaign_id}", flush=True)


def run_campaign(
    *,
    campaign_id: str | None,
    invocation_attempts: int,
    artifact_dir: Path,
    stop_file: Path,
    poll_s: float,
    heartbeat_s: float,
    oracle_timeout_s: float,
) -> str:
    if not 1 <= invocation_attempts <= TOTAL_ATTEMPT_BUDGET:
        raise ValueError("invocation_attempts must be between 1 and 60")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=artifact_dir / "run.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    client = BoMcpClient.from_env(timeout_s=120.0)
    campaign_id = _campaign(client, campaign_id)
    print(f"[EVENT] campaign ready campaign_id={campaign_id} backend=baybe", flush=True)
    logfire.info("Direct arylation campaign active", campaign_id=campaign_id, nonce=CACHE_BUSTER)
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(heartbeat_stop, heartbeat_s, campaign_id), daemon=True
    )
    heartbeat.start()
    completed_this_invocation = 0
    try:
        while completed_this_invocation < invocation_attempts:
            if stop_file.exists():
                print(f"[EVENT] stop requested by {stop_file}", flush=True)
                stop_file.unlink()
                break
            attempts = collect_attempts(client, campaign_id)
            if len(attempts) >= TOTAL_ATTEMPT_BUDGET:
                print("[EVENT] exact 60-attempt benchmark budget reached", flush=True)
                break
            suggestion = _next_suggestion(client, campaign_id, poll_s)
            if suggestion is None:
                if client.next_action(campaign_id).get("action") in {"wait", "retry", "poll"}:
                    continue
                break
            candidate = normalize_candidate(suggestion["parameter_values"])
            suggestion_id = suggestion["suggestion_id"]
            try:
                measured_yield = evaluate(candidate, oracle_timeout_s)
            except EvaluationFailure as exc:
                record = {
                    "campaign_id": campaign_id,
                    "suggestion_id": suggestion_id,
                    "status": "failed",
                    "parameter_values": candidate,
                    "objective_values": {"yield": None},
                    "error": str(exc),
                }
                append_attempt(artifact_dir / "attempts.jsonl", record)
                client.update_suggestion_status(suggestion_id, "rejected")
                completed_this_invocation += 1
                print(f"[ALERT] evaluation failed suggestion_id={suggestion_id}: {exc}", flush=True)
                print(f"[RESULT] {json.dumps(record, sort_keys=True)}", flush=True)
                continue
            record = {
                "campaign_id": campaign_id,
                "suggestion_id": suggestion_id,
                "status": "success",
                "parameter_values": candidate,
                "objective_values": {"yield": measured_yield},
                "error": None,
            }
            append_attempt(artifact_dir / "attempts.jsonl", record)
            result = {
                "suggestion_id": suggestion_id,
                "parameter_values": candidate,
                "objective_values": {"yield": measured_yield},
            }
            submit_key = str(uuid5(NAMESPACE_URL, f"{campaign_id}:{suggestion_id}:submit"))
            client.submit_results(
                campaign_id,
                results=[result],
                idempotency_key=submit_key,
                force=True,
            )
            completed_this_invocation += 1
            print(f"[RESULT] {json.dumps(record, sort_keys=True)}", flush=True)
        attempts = collect_attempts(client, campaign_id)
        report = write_final_report(artifact_dir / "final_report.json", campaign_id, attempts)
        print(
            "[RESULT] summary="
            + json.dumps(
                {
                    "attempted": report["attempted_evaluations"],
                    "successful": report["successful_evaluations"],
                    "best_measured_yield": report["best_measured_yield"],
                    "best_reaction_conditions": report["best_reaction_conditions"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        _pause_if_running(client, campaign_id)
        return campaign_id
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=1.0)
