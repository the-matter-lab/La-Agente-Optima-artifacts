"""Orchestrator: runs the direct-arylation-yield BO-MCP campaign loop.

Loop-state ownership is BO-MCP's: `next_action` decides continue/stop, and
the local attempt counter only bounds *this invocation* against the
user-requested 60-attempt budget (an oracle attempt, success or failure,
consumes one unit). The JSONL artifact is append-only provenance; it is read
back once at startup only to recover locally-tracked failed-attempt counts
that BO-MCP itself does not persist (server results only ever hold
successful, finite measurements).
"""
import os
import time

import requests

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .oracle import evaluate_candidate
from .reporting import append_jsonl, build_summary, print_result_line, read_jsonl, write_summary
from .search_space import CAMPAIGN_NAME, OBJECTIVE_NAME, build_intake


def _generate_batch(client, campaign_id, batch_size, poll_s, heartbeat_s, max_polls=20):
    """Ask BO-MCP for `batch_size` suggestions, recovering from slow/timed-out generation."""
    try:
        resp = client.generate_suggestions(campaign_id, batch_size=batch_size)
    except requests.exceptions.RequestException as exc:
        print(f"[EVENT] generate_suggestions transport issue ({exc}); "
              f"polling pending suggestions every {poll_s}s", flush=True)
        last_hb = time.monotonic()
        for _ in range(max_polls):
            time.sleep(poll_s)
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            if pending:
                return pending[:batch_size]
            now = time.monotonic()
            if now - last_hb >= heartbeat_s:
                print("[HEARTBEAT] still waiting on suggestion generation", flush=True)
                last_hb = now
        print("[ALERT] no suggestions materialized after polling; stopping loop", flush=True)
        return []

    if not resp.get("success", True):
        print(f"[ALERT] generate_suggestions rejected: {resp.get('errors')}", flush=True)
        return []
    return resp.get("suggestions", [])


def run(*, campaign_id, max_attempts, batch_size, initial_design_size,
        poll_s, heartbeat_s, stop_file, artifact_path, summary_path):
    client = BoMcpClient.from_env()

    if campaign_id is None:
        intake = build_intake(batch_size=batch_size, initial_design_size=initial_design_size)
        validation = client.validate_intake(intake)
        if not validation.get("valid", True):
            print(f"[ALERT] intake validation failed: {validation.get('errors')}", flush=True)
            return None
        resp = client.create_campaign(
            intake, idempotency_key=client.make_idempotency_key("create", CAMPAIGN_NAME)
        )
        campaign_id = resp["campaign_id"]
        print(f"[EVENT] created campaign campaign_id={campaign_id} name={CAMPAIGN_NAME}", flush=True)
    else:
        print(f"[EVENT] resuming campaign_id={campaign_id}", flush=True)
        current = client.get_campaign(campaign_id)
        if current.get("status") == "paused":
            client.lifecycle(campaign_id, action="resume")
        elif current.get("status") == "completed":
            client.lifecycle(campaign_id, action="reopen")

    prior_records = [r for r in read_jsonl(artifact_path) if r.get("campaign_id") == campaign_id]
    prior_failed = sum(1 for r in prior_records if r["status"] == "failed")
    prior_success = len(client.get_results(campaign_id))
    attempts_used = prior_success + prior_failed
    print(f"[EVENT] attempts_used_so_far={attempts_used} "
          f"(server_success={prior_success} local_failed={prior_failed}) budget={max_attempts}", flush=True)

    last_heartbeat = time.monotonic()

    while attempts_used < max_attempts:
        if os.path.exists(stop_file):
            print("[EVENT] stop file detected; pausing before generating the next suggestion batch", flush=True)
            os.remove(stop_file)
            break

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            print(f"[EVENT] server next_action={decision.get('action')!r}; stopping loop", flush=True)
            break

        remaining = max_attempts - attempts_used
        this_batch = min(batch_size, remaining)
        suggestions = _generate_batch(client, campaign_id, this_batch, poll_s, heartbeat_s)
        if not suggestions:
            print("[ALERT] no suggestions available; stopping loop", flush=True)
            break
        suggestions = suggestions[:this_batch]

        results_payload = []
        for sug in suggestions:
            params = sug["parameter_values"]
            outcome = evaluate_candidate(params)
            attempts_used += 1
            record = {
                "campaign_id": campaign_id,
                "suggestion_id": sug.get("suggestion_id"),
                "parameter_values": params,
                "status": outcome["status"],
                "yield": outcome["yield"],
                "http_status": outcome["http_status"],
                "error": outcome["error"],
            }
            append_jsonl(artifact_path, record)
            print_result_line(record)
            if outcome["status"] == "success":
                results_payload.append({
                    "suggestion_id": sug.get("suggestion_id"),
                    "parameter_values": params,
                    "objective_values": {OBJECTIVE_NAME: outcome["yield"]},
                })
            else:
                print(f"[ALERT] oracle evaluation failed suggestion_id={sug.get('suggestion_id')} "
                      f"error={outcome['error']!r}", flush=True)
                try:
                    client.update_suggestion_status(sug["suggestion_id"], "rejected")
                except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never fatal
                    print(f"[ALERT] could not mark suggestion rejected: {exc}", flush=True)

        if results_payload:
            try:
                sub = client.submit_results(
                    campaign_id,
                    results=results_payload,
                    idempotency_key=client.make_idempotency_key("submit", campaign_id, str(attempts_used)),
                )
                if not sub.get("success", True):
                    print(f"[ALERT] submit_results rejected: {sub.get('errors')}", flush=True)
            except BoMcpOperationError as exc:
                print(f"[ALERT] submit_results operation error: {exc}", flush=True)

        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            print(f"[HEARTBEAT] attempts_used={attempts_used}/{max_attempts}", flush=True)
            last_heartbeat = now

    print(f"[EVENT] loop finished attempts_used={attempts_used}/{max_attempts}", flush=True)

    campaign = client.get_campaign(campaign_id)
    if campaign.get("status") == "running":
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] campaign paused campaign_id={campaign_id}", flush=True)
    else:
        print(f"[EVENT] campaign status={campaign.get('status')!r}; no pause needed", flush=True)

    all_records = [r for r in read_jsonl(artifact_path) if r.get("campaign_id") == campaign_id]
    summary = build_summary(campaign_id, all_records)
    write_summary(summary_path, summary)

    print(f"[RESULT] SUMMARY campaign_id={campaign_id} attempted={summary['attempted']} "
          f"successful={summary['successful']} failed={summary['failed']} "
          f"best_yield_percent={summary['best_yield_percent']} "
          f"best_conditions={summary['best_conditions']}", flush=True)
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)

    return campaign_id
