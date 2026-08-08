import json
import logging
import time
import uuid
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate
from .intake import OWNERSHIP_MARKER, TOTAL_ATTEMPT_BUDGET, build_intake
from .reporting import append_evaluation, write_reports
from .search_space import PARAMETER_NAMES


def _campaign_payload(response: dict) -> dict:
    return response.get("campaign", response.get("data", response))


def _status(client: BoMcpClient, campaign_id: str) -> str:
    payload = _campaign_payload(client.get_campaign(campaign_id))
    return str(payload.get("status", "")).lower()


def _point(values: dict) -> tuple[float, ...]:
    return tuple(round(float(values[name]), 15) for name in PARAMETER_NAMES)


def _server_counts(client: BoMcpClient, campaign_id: str) -> tuple[int, int, list[dict], list[dict]]:
    results = client.get_results(campaign_id)
    rejected = client.query_suggestions(campaign_id, status_filter="rejected", limit=500)
    return len(results) + len(rejected), len(results), results, rejected


def _seen_points(results: list[dict], rejected: list[dict], expired: list[dict]) -> set[tuple[float, ...]]:
    rows = [*results, *rejected, *expired]
    return {_point(row["parameter_values"]) for row in rows if row.get("parameter_values")}


def _owned_name(client: BoMcpClient, campaign_id: str) -> str:
    payload = _campaign_payload(client.get_campaign(campaign_id))
    return str(payload.get("name") or payload.get("spec", {}).get("name") or "")


def run_campaign(
    *,
    campaign_id: str | None,
    artifact_dir: Path,
    batch_size: int,
    invocation_attempt_limit: int | None,
    poll_s: int,
    heartbeat_s: int,
    stop_file: Path,
) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=artifact_dir / "run.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    evaluations_path = artifact_dir / "evaluations.jsonl"
    client = BoMcpClient.from_env()

    if campaign_id is None:
        intake = build_intake()
        client.validate_intake(intake)
        created = client.create_campaign(intake, idempotency_key=f"{OWNERSHIP_MARKER}-create-{uuid.uuid4()}")
        campaign_id = created["campaign_id"]
        print(f"[EVENT] created campaign_id={campaign_id} marker={OWNERSHIP_MARKER}", flush=True)
    else:
        name = _owned_name(client, campaign_id)
        if OWNERSHIP_MARKER not in name:
            raise RuntimeError(f"Refusing campaign without ownership marker: {campaign_id}")
        status = _status(client, campaign_id)
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            print(f"[EVENT] resumed campaign_id={campaign_id}", flush=True)
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            print(f"[EVENT] reopened campaign_id={campaign_id}", flush=True)

    (artifact_dir / "campaign_id.txt").write_text(campaign_id + "\n")
    attempted_at_start, _, _, _ = _server_counts(client, campaign_id)
    invocation_attempts = 0
    last_heartbeat = time.monotonic()

    try:
        while True:
            if stop_file.exists():
                print(f"[EVENT] stop file observed at {stop_file}; pausing normally", flush=True)
                stop_file.unlink()
                break

            attempted, successful, results, rejected = _server_counts(client, campaign_id)
            if attempted >= TOTAL_ATTEMPT_BUDGET:
                print(f"[EVENT] total attempted budget reached attempted={attempted} successful={successful}", flush=True)
                break
            if invocation_attempt_limit is not None and invocation_attempts >= invocation_attempt_limit:
                print(f"[EVENT] invocation attempt limit reached attempts_this_run={invocation_attempts}", flush=True)
                break
            if time.monotonic() - last_heartbeat >= heartbeat_s:
                print(f"[HEARTBEAT] campaign_id={campaign_id} attempted={attempted} successful={successful}", flush=True)
                last_heartbeat = time.monotonic()

            pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
            if not pending:
                decision = client.next_action(campaign_id)
                action = decision.get("action")
                if action != "bo_generate_suggestions":
                    print(f"[ALERT] BO-MCP next_action={action} before attempted budget {attempted}/{TOTAL_ATTEMPT_BUDGET}", flush=True)
                    if action in {"wait", "bo_wait"}:
                        time.sleep(poll_s)
                        continue
                    break
                remaining_total = TOTAL_ATTEMPT_BUDGET - attempted
                remaining_invocation = remaining_total if invocation_attempt_limit is None else invocation_attempt_limit - invocation_attempts
                requested = max(1, min(batch_size, remaining_total, remaining_invocation))
                generated = client.generate_suggestions(campaign_id, batch_size=requested)
                pending = generated.get("suggestions", [])
                print(f"[EVENT] generated suggestions count={len(pending)} requested={requested}", flush=True)

            expired = client.query_suggestions(campaign_id, status_filter="expired", limit=500)
            seen = _seen_points(results, rejected, expired)
            for suggestion in pending:
                attempted, successful, _, _ = _server_counts(client, campaign_id)
                if attempted >= TOTAL_ATTEMPT_BUDGET or (invocation_attempt_limit is not None and invocation_attempts >= invocation_attempt_limit):
                    break
                suggestion_id = suggestion["suggestion_id"]
                parameters = {name: float(suggestion["parameter_values"][name]) for name in PARAMETER_NAMES}
                point = _point(parameters)
                if point in seen:
                    client.update_suggestion_status(suggestion_id, "expired")
                    print(f"[EVENT] expired duplicate suggestion_id={suggestion_id}", flush=True)
                    continue

                evaluation_index = attempted + 1
                try:
                    values = evaluate(parameters)
                    result = {
                        "parameter_values": parameters,
                        "objective_values": {"surface_response": values["surface_response"]},
                        "suggestion_id": suggestion_id,
                        "metadata": {
                            "experiment_id": f"evaluation-{evaluation_index:03d}",
                            "conditions": {"raw_response": values["raw_response"]},
                            "notes": "Deterministic Ackley 6D synthetic benchmark.",
                        },
                    }
                    client.submit_results(
                        campaign_id,
                        results=[result],
                        idempotency_key=f"{campaign_id}-evaluation-{evaluation_index:03d}-{uuid.uuid4()}",
                    )
                    row = {
                        "evaluation_index": evaluation_index,
                        "parameter_values": parameters,
                        "objective_values": {"surface_response": values["surface_response"]},
                        "status": "success",
                        "failure_reason": None,
                        "raw_response": values["raw_response"],
                    }
                    seen.add(point)
                except Exception as exc:
                    client.update_suggestion_status(suggestion_id, "rejected")
                    row = {
                        "evaluation_index": evaluation_index,
                        "parameter_values": parameters,
                        "objective_values": {},
                        "status": "failed",
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                        "raw_response": None,
                    }
                    print(f"[ALERT] evaluation failed index={evaluation_index} reason={row['failure_reason']}", flush=True)
                append_evaluation(evaluations_path, row)
                invocation_attempts += 1
                print(f"[RESULT] {json.dumps(row, sort_keys=True)}", flush=True)
                logfire.info("Ackley evaluation completed", campaign_id=campaign_id, evaluation_index=evaluation_index, status=row["status"])
    finally:
        summary = write_reports(evaluations_path, artifact_dir, campaign_id)
        status = _status(client, campaign_id)
        if status == "running":
            client.lifecycle(campaign_id, action="pause")
            print(f"[EVENT] paused campaign_id={campaign_id}", flush=True)
        print(
            f"[EVENT] artifacts={artifact_dir} attempted_this_campaign={summary['attempted_evaluations']} successful={summary['successful_evaluations']}",
            flush=True,
        )
        logging.info("campaign_id=%s attempted_at_start=%s invocation_attempts=%s", campaign_id, attempted_at_start, invocation_attempts)
    return campaign_id
