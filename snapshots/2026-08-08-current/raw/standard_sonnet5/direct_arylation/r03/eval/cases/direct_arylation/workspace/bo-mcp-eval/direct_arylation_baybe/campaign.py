"""Orchestrator: runs the direct-arylation-yield BO-MCP campaign (BayBE backend).

Loop-state ownership is BO-MCP's: `next_action` decides continue/stop, and
the count of non-pending suggestions already on the server (server truth,
never a local file) bounds this invocation against the requested attempt
budget. The JSONL artifact is append-only provenance and is never read back
to steer the loop. The stop-file is checked only at the top of an iteration
(before generating/reusing a suggestion), never between evaluation and
result submission.
"""
import os
import time

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .intake import CAMPAIGN_NAME, OBJECTIVE_NAME, build_intake
from .oracle import evaluate_candidate
from .reporting import append_jsonl, build_summary, print_attempt, print_summary, write_summary


def _attempts_used(client, campaign_id: str) -> int:
    suggestions = client.query_suggestions(campaign_id, limit=500)
    return sum(1 for s in suggestions if s.get("status") != "pending")


def _pending_suggestions(client, campaign_id: str, max_needed: int) -> list:
    subs = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
    return subs[:max_needed]


def run(*, campaign_id, budget, batch_size, initial_design_size,
        poll_s, heartbeat_s, stop_file, artifact_path, summary_path):
    client = BoMcpClient.from_env()

    if campaign_id is None:
        intake = build_intake(batch_size=batch_size, initial_design_size=initial_design_size)
        validation = client.validate_intake(intake)
        if not validation.get("valid", True):
            print(f"[ALERT] intake validation failed: {validation.get('errors')}", flush=True)
            raise SystemExit(2)
        resp = client.create_campaign(
            intake, idempotency_key=client.make_idempotency_key("create", CAMPAIGN_NAME)
        )
        if not resp.get("success", True):
            print(f"[ALERT] campaign creation rejected: {resp.get('errors')}", flush=True)
            raise SystemExit(2)
        campaign_id = resp["campaign_id"]
        print(f"[EVENT] created campaign_id={campaign_id} name={CAMPAIGN_NAME}", flush=True)
    else:
        print(f"[EVENT] resuming campaign_id={campaign_id}", flush=True)
        current = client.get_campaign(campaign_id)
        if current.get("status") == "paused":
            client.lifecycle(campaign_id, action="resume")
            print("[EVENT] campaign resumed", flush=True)
        elif current.get("status") == "completed":
            client.lifecycle(campaign_id, action="reopen")
            print("[EVENT] campaign reopened", flush=True)

    attempts_used = _attempts_used(client, campaign_id)
    print(f"[EVENT] attempts_used_so_far={attempts_used}/{budget} (server truth)", flush=True)

    last_heartbeat = time.monotonic()

    while attempts_used < budget:
        if os.path.exists(stop_file):
            print(f"[EVENT] stop file {stop_file!r} detected; pausing before next suggestion", flush=True)
            os.remove(stop_file)
            break

        remaining = budget - attempts_used
        batch = _pending_suggestions(client, campaign_id, remaining)
        if batch:
            print(f"[EVENT] reusing {len(batch)} previously-generated pending suggestion(s)", flush=True)
        else:
            decision = client.next_action(campaign_id)
            if decision.get("action") != "bo_generate_suggestions":
                print(f"[ALERT] stop condition from server: action={decision.get('action')} "
                      f"reason={decision.get('reason')}", flush=True)
                break
            this_batch = min(batch_size, remaining)
            gen = client.generate_suggestions(
                campaign_id, batch_size=this_batch, timeout_s=max(poll_s * 2, 120)
            )
            if not gen.get("success", True):
                print(f"[ALERT] suggestion generation rejected: {gen.get('errors')}", flush=True)
                break
            batch = gen.get("suggestions") or []
            if not batch:
                print("[ALERT] no suggestions returned; stopping loop", flush=True)
                break

        for sugg in batch:
            if attempts_used >= budget:
                break
            params = sugg["parameter_values"]
            outcome = evaluate_candidate(params)
            attempts_used += 1

            append_jsonl(artifact_path, {
                "campaign_id": campaign_id,
                "suggestion_id": sugg.get("suggestion_id"),
                "parameters": params,
                "status": outcome["status"],
                "yield_percent": outcome["yield"],
                "error": outcome["error"],
            })
            print_attempt(attempts_used, budget, outcome["status"], params, outcome["yield"], outcome["error"])

            if outcome["status"] == "success":
                try:
                    sub = client.submit_results(
                        campaign_id,
                        results=[{
                            "suggestion_id": sugg.get("suggestion_id"),
                            "parameter_values": params,
                            "objective_values": {OBJECTIVE_NAME: outcome["yield"]},
                        }],
                        idempotency_key=client.make_idempotency_key(
                            "submit", campaign_id, str(sugg.get("suggestion_id", attempts_used))
                        ),
                    )
                    if not sub.get("success", True):
                        print(f"[ALERT] submit_results rejected suggestion_id="
                              f"{sugg.get('suggestion_id')}: {sub.get('errors')}", flush=True)
                except BoMcpOperationError as exc:
                    print(f"[ALERT] submit_results operation error: {exc}", flush=True)
            else:
                try:
                    client.update_suggestion_status(sugg["suggestion_id"], "rejected")
                except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never fatal
                    print(f"[ALERT] could not mark suggestion rejected: {exc}", flush=True)

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_s:
                print(f"[HEARTBEAT] attempts_used={attempts_used}/{budget}", flush=True)
                last_heartbeat = now

    print(f"[EVENT] loop ended attempts_used={attempts_used}/{budget}", flush=True)

    status_now = client.get_campaign(campaign_id).get("status")
    if status_now == "running":
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] campaign paused campaign_id={campaign_id}", flush=True)
    else:
        print(f"[EVENT] campaign status={status_now!r}; no pause needed", flush=True)

    summary = build_summary(client, campaign_id)
    write_summary(summary_path, summary)
    print_summary(summary)
    print(f"[EVENT] BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)

    return campaign_id, summary
