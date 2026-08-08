import json
import logging
import time
import uuid
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate_ackley
from .intake import OWNERSHIP_MARKER, build_intake
from .reporting import append_evaluation, load_evaluations, write_reports
from .search_space import point_key


def _emit(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def _owned_campaign(client: BoMcpClient, campaign_id: str) -> dict:
    campaign = client.get_campaign(campaign_id)
    if OWNERSHIP_MARKER not in campaign.get("name", ""):
        raise RuntimeError(
            f"refusing campaign {campaign_id}: required ownership marker is absent"
        )
    return campaign


def _activate(client: BoMcpClient, campaign_id: str) -> None:
    status = _owned_campaign(client, campaign_id)["status"]
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        _emit("EVENT", f"resumed campaign_id={campaign_id}")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        _emit("EVENT", f"reopened campaign_id={campaign_id}")
    elif status != "running":
        raise RuntimeError(f"campaign {campaign_id} cannot run from status={status}")


def _known_points(client: BoMcpClient, campaign_id: str) -> set[tuple[str, ...]]:
    known = set()
    for result in client.get_results(campaign_id):
        known.add(point_key(result["parameter_values"]))
    for suggestion in client.query_suggestions(campaign_id, limit=500):
        if suggestion.get("status") in {"completed", "rejected", "expired"}:
            known.add(point_key(suggestion["parameter_values"]))
    return known


def _shutdown(client: BoMcpClient, campaign_id: str) -> None:
    campaign = _owned_campaign(client, campaign_id)
    if campaign["status"] == "running":
        client.lifecycle(campaign_id, action="pause")
        _emit("EVENT", f"paused campaign_id={campaign_id}")


def run_campaign(args) -> None:
    if args.max_attempts < 1:
        raise ValueError("--max-attempts must be positive")
    if not 120 <= args.poll_s <= 300:
        raise ValueError("--poll-s must be within 120..300 seconds")

    client = BoMcpClient.from_env()
    campaign_id = args.campaign_id
    if campaign_id:
        _activate(client, campaign_id)
    else:
        intake = build_intake()
        validation = client.validate_intake(intake)
        if not validation.get("valid"):
            raise RuntimeError(f"intake rejected: {validation.get('errors')}")
        created = client.create_campaign(
            intake,
            idempotency_key=f"{OWNERSHIP_MARKER}-create-{uuid.uuid4()}",
        )
        campaign_id = created["campaign_id"]
        _emit("EVENT", f"created campaign_id={campaign_id} backend=baybe")

    artifact_dir = args.artifact_root / campaign_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "run.log"
    logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logfire.info("Ackley campaign invocation started", campaign_id=campaign_id)
    _emit("EVENT", f"campaign_id={campaign_id} artifacts={artifact_dir}")

    artifact_path = artifact_dir / "evaluations.jsonl"
    next_index = len(load_evaluations(artifact_path)) + 1
    attempted = 0
    last_heartbeat = time.monotonic()

    try:
        while attempted < args.max_attempts:
            if args.stop_file.exists():
                _emit("EVENT", f"stop file detected at {args.stop_file}; pausing normally")
                args.stop_file.unlink()
                break

            if time.monotonic() - last_heartbeat >= args.heartbeat_s:
                _emit("HEARTBEAT", f"campaign_id={campaign_id} invocation_attempted={attempted}/{args.max_attempts}")
                last_heartbeat = time.monotonic()

            pending = client.query_suggestions(campaign_id, status_filter="pending", limit=100)
            if pending:
                suggestions = pending[: args.max_attempts - attempted]
                _emit("EVENT", f"reusing pending suggestions count={len(suggestions)}")
            else:
                decision = client.next_action(campaign_id)
                if decision.get("action") != "bo_generate_suggestions":
                    if decision.get("action") in {"wait", "retry_later"}:
                        _emit("EVENT", f"server requested wait; sleeping {args.poll_s}s")
                        time.sleep(args.poll_s)
                        continue
                    _emit("ALERT", f"server stop action={decision.get('action')} reason={decision.get('reason')}")
                    break
                remaining = args.max_attempts - attempted
                batch_size = min(6 if int(decision.get("n_results") or 0) < 12 else 4, remaining)
                generated = client.generate_suggestions(campaign_id, batch_size=batch_size)
                suggestions = generated["suggestions"]
                _emit("EVENT", f"generated suggestions count={len(suggestions)} batch_size={batch_size}")

            known = _known_points(client, campaign_id)
            accepted_this_batch: set[tuple[str, ...]] = set()
            for suggestion in suggestions:
                if attempted >= args.max_attempts:
                    break
                suggestion_id = suggestion["suggestion_id"]
                parameters = suggestion["parameter_values"]
                key = point_key(parameters)
                if key in known or key in accepted_this_batch:
                    client.update_suggestion_status(suggestion_id, "rejected")
                    _emit("EVENT", f"rejected duplicate suggestion_id={suggestion_id}")
                    continue

                attempted += 1
                known.add(key)
                row = {
                    "evaluation_index": next_index,
                    "parameter_values": {name: float(value) for name, value in parameters.items()},
                    "objective_values": {},
                    "status": "failed",
                    "failure_reason": None,
                    "raw_response": None,
                    "suggestion_id": suggestion_id,
                }
                try:
                    evaluated = evaluate_ackley(parameters)
                    row["parameter_values"] = evaluated["parameter_values"]
                    row["raw_response"] = evaluated["raw_response"]
                    row["objective_values"] = {
                        "surface_response": evaluated["surface_response"]
                    }
                    client.submit_results(
                        campaign_id,
                        results=[
                            {
                                "suggestion_id": suggestion_id,
                                "parameter_values": evaluated["parameter_values"],
                                "objective_values": {
                                    "surface_response": evaluated["surface_response"]
                                },
                                "metadata": {
                                    "notes": "noiseless normalized Ackley synthetic benchmark"
                                },
                            }
                        ],
                        idempotency_key=f"{OWNERSHIP_MARKER}-submit-{suggestion_id}",
                    )
                    row["status"] = "success"
                    accepted_this_batch.add(key)
                    known.add(key)
                except Exception as exc:
                    row["failure_reason"] = f"{type(exc).__name__}: {exc}"
                    try:
                        client.update_suggestion_status(suggestion_id, "rejected")
                    except Exception:
                        logging.exception("Failed to reject suggestion %s", suggestion_id)
                    _emit("ALERT", f"evaluation_index={next_index} failed reason={row['failure_reason']}")

                append_evaluation(artifact_path, row)
                _emit("RESULT", json.dumps(row, sort_keys=True, separators=(",", ":")))
                logging.info("evaluation=%s", json.dumps(row, sort_keys=True))
                next_index += 1

        summary = write_reports(artifact_dir, campaign_id)
        try:
            blob, _ = client.export_campaign(campaign_id, fmt="csv")
            (artifact_dir / "bo_mcp_export.csv").write_bytes(blob)
        except Exception as exc:
            _emit("ALERT", f"campaign export failed: {type(exc).__name__}: {exc}")
        _emit("RESULT", json.dumps(summary, sort_keys=True, separators=(",", ":")))
    finally:
        _shutdown(client, campaign_id)
        logfire.info("Ackley campaign invocation ended", campaign_id=campaign_id, attempted=attempted)
