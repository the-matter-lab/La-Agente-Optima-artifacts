"""Orchestration: BO-MCP loop for the direct arylation yield campaign."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from . import artifacts, intake, space
from .evaluation import evaluate

CONTINUE_ACTION = "bo_generate_suggestions"


def _ensure_running(client: BoMcpClient, campaign_id: str, reporter: artifacts.Reporter) -> None:
    status = client.next_action(campaign_id)["status"]
    action = {"paused": "resume", "completed": "reopen"}.get(status)
    if action:
        client.lifecycle(campaign_id, action=action)
        reporter.event(f"campaign {campaign_id} {status} -> {action}d")


def _submit(client: BoMcpClient, campaign_id: str, rows: list[dict[str, Any]], tag: str) -> None:
    key = BoMcpClient.make_idempotency_key("res", campaign_id, tag)
    try:
        client.submit_results(campaign_id, results=rows, idempotency_key=key)
    except BoMcpOperationError as exc:
        # Optimizer-requested replicate: resubmit forced under a fresh key.
        client.submit_results(
            campaign_id,
            results=rows,
            idempotency_key=BoMcpClient.make_idempotency_key("res", campaign_id, tag, "force"),
            force=True,
        )
        del exc


def run(cfg) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    reporter = artifacts.Reporter(stamp)
    stop_file = Path(cfg.stop_file)
    client = BoMcpClient.from_env(timeout_s=cfg.request_timeout_s)

    if stop_file.exists():
        stop_file.unlink()
        reporter.event(f"stop file {stop_file} present at startup -> nothing to do")
        return artifacts.summarize(cfg.campaign_id or "", reporter.load_attempts())

    campaign_id = cfg.campaign_id
    if campaign_id:
        _ensure_running(client, campaign_id, reporter)
        reporter.event(f"resuming campaign {campaign_id}")
    else:
        payload = intake.build_intake(
            batch_size=cfg.batch_size,
            initial_design_size=cfg.initial_design_size,
            random_seed=cfg.random_seed,
        )
        client.validate_intake(payload)
        created = client.create_campaign(
            payload, idempotency_key=BoMcpClient.make_idempotency_key("camp", payload["name"], stamp)
        )
        campaign_id = created["campaign_id"]
        reporter.event(f"created campaign {campaign_id} ({payload['name']})")

    oracle_url = os.environ["DIRECT_ARYLATION_API_URL"]
    attempts: list[dict[str, Any]] = []
    successes = 0
    best = float("-inf")
    last_beat = time.time()

    while len(attempts) < cfg.max_attempts:
        if stop_file.exists():
            stop_file.unlink()
            reporter.event(f"stop file {stop_file} found -> shutting down after {len(attempts)} attempts")
            break

        decision = client.next_action(campaign_id)
        if decision["action"] != CONTINUE_ACTION:
            reporter.alert(
                f"server stops the loop: action={decision['action']} status={decision['status']} "
                f"reason={decision.get('reason')}"
            )
            break
        if (decision["n_results"] or 0) >= cfg.max_successes:
            reporter.event(f"server holds {decision['n_results']} results >= cap {cfg.max_successes}")
            break

        batch = min(cfg.batch_size, cfg.max_attempts - len(attempts))
        generated = client.generate_suggestions(campaign_id, batch_size=batch)
        suggestions = generated.get("suggestions") or client.query_suggestions(
            campaign_id, status_filter="pending"
        )
        if not suggestions:
            reporter.alert(f"no suggestions returned; retrying in {cfg.poll_s}s")
            time.sleep(cfg.poll_s)
            continue

        rows: list[dict[str, Any]] = []
        for suggestion in suggestions[:batch]:
            payload = space.oracle_payload(suggestion["parameter_values"])
            record = evaluate(
                payload,
                base_url=oracle_url,
                objective_name=space.OBJECTIVE_NAME,
                timeout_s=cfg.oracle_timeout_s,
            )
            record["suggestion_id"] = suggestion["suggestion_id"]
            record["attempt"] = len(attempts) + 1
            record["attempt_budget"] = cfg.max_attempts
            record["iteration"] = generated.get("iteration")
            if record["status"] == "success":
                successes += 1
                best = max(best, record["objective_values"]["yield"])
                rows.append(
                    {
                        "parameter_values": record["parameter_values"],
                        "objective_values": record["objective_values"],
                        "suggestion_id": suggestion["suggestion_id"],
                    }
                )
            record["successes"] = successes
            record["best_yield"] = best
            attempts.append(record)
            reporter.record_attempt(record)
            reporter.result(record)
            if record["status"] != "success":
                reporter.alert(f"oracle failure on attempt {record['attempt']}: {record.get('error')}")
                client.update_suggestion_status(suggestion["suggestion_id"], "rejected")

        if rows:
            _submit(client, campaign_id, rows, f"{stamp}-{len(attempts)}")

        if time.time() - last_beat >= cfg.heartbeat_s:
            reporter.heartbeat(
                f"alive: {len(attempts)}/{cfg.max_attempts} attempts, best={best:.2f}%"
            )
            last_beat = time.time()

    if client.next_action(campaign_id)["status"] == "running":
        client.lifecycle(campaign_id, action="pause")
        reporter.event(f"campaign {campaign_id} paused (resume by re-running with --campaign-id)")

    all_attempts = reporter.load_attempts()
    report = artifacts.summarize(campaign_id, all_attempts)
    reporter.write_snapshot(all_attempts)

    reporter.write_report(report)
    artifacts.print_summary(reporter, report)
    return report
