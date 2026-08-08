"""Orchestrates the BO-MCP campaign loop for the Ackley 6D benchmark.

Loop-state ownership: BO-MCP (via `next_action`) decides continue/stop.
The local JSONL artifact is the append-only evaluation ledger; per this
task's explicit counting rule, an evaluation counts toward the fixed
60-evaluation budget once it is either submitted to BO-MCP or written to
the local artifact, so the artifact row count is also this script's
budget gate (not a generic "re-derive BO progress" shortcut).
"""
import os
import time

from domains.bo_mcp.client import BoMcpClient

from .intake import OWNERSHIP_MARKER, build_intake
from .objective import evaluate_candidate
from .reporting import append_row, artifact_paths, load_rows, make_row, print_summary, summarize
from .search_space import PARAM_NAMES

TOTAL_BUDGET = 60


def _check_stop_file(stop_file: str) -> bool:
    if os.path.exists(stop_file):
        print(f"[EVENT] stop file '{stop_file}' detected; will pause after current step")
        os.remove(stop_file)
        return True
    return False


def _ensure_marker(name: str, campaign_id: str) -> None:
    if OWNERSHIP_MARKER not in name:
        raise RuntimeError(
            f"[ALERT] refusing to operate on campaign {campaign_id}: "
            f"name '{name}' is missing ownership marker '{OWNERSHIP_MARKER}'"
        )


def _get_or_create_campaign(client: BoMcpClient, campaign_id: str | None) -> tuple[str, str]:
    if campaign_id:
        info = client.get_campaign(campaign_id)
        name = info.get("name", "")
        _ensure_marker(name, campaign_id)
        print(f"[EVENT] resuming campaign_id={campaign_id} name={name} status={info.get('status')}")
        if info.get("status") == "paused":
            client.lifecycle(campaign_id, action="resume")
            print(f"[EVENT] campaign_id={campaign_id} resumed from paused")
        elif info.get("status") == "completed":
            client.lifecycle(campaign_id, action="reopen")
            print(f"[EVENT] campaign_id={campaign_id} reopened from completed")
        return campaign_id, name

    intake = build_intake()
    validation = client.validate_intake(intake)
    if not validation.get("success", True):
        raise RuntimeError(f"[ALERT] intake validation failed: {validation.get('errors')}")
    idem_key = client.make_idempotency_key("ackley6d-create", intake["name"])
    created = client.create_campaign(intake, idempotency_key=idem_key)
    if not created.get("success"):
        raise RuntimeError(f"[ALERT] campaign creation failed: {created.get('errors')}")
    new_id = created["campaign_id"]
    _ensure_marker(intake["name"], new_id)
    print(f"[EVENT] created campaign_id={new_id} name={intake['name']}")
    return new_id, intake["name"]


def run(campaign_id: str | None, artifact_dir: str, poll_s: int, heartbeat_s: int, stop_file: str) -> str:
    client = BoMcpClient.from_env()
    campaign_id, name = _get_or_create_campaign(client, campaign_id)

    jsonl_path, csv_path = artifact_paths(artifact_dir, campaign_id)
    rows = load_rows(jsonl_path)
    attempted = len(rows)
    print(f"[EVENT] artifact={jsonl_path} attempted_so_far={attempted}/{TOTAL_BUDGET}")

    last_heartbeat = time.monotonic()

    while attempted < TOTAL_BUDGET:
        if _check_stop_file(stop_file):
            _pause_if_running(client, campaign_id)
            print("[EVENT] shutdown after stop-file request")
            break

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            print(f"[EVENT] server action='{decision.get('action')}' reason='{decision.get('reason')}'; stopping")
            break

        remaining = TOTAL_BUDGET - attempted
        batch_size = min(6, remaining)
        try:
            gen = client.generate_suggestions(campaign_id, batch_size=batch_size)
        except Exception as exc:
            print(f"[ALERT] suggestion generation failed: {exc}")
            time.sleep(min(poll_s, 30))
            continue
        if not gen.get("success"):
            print(f"[ALERT] suggestion generation rejected: {gen.get('errors')}")
            break

        for suggestion in gen.get("suggestions", []):
            if attempted >= TOTAL_BUDGET:
                break
            suggestion_id = suggestion["suggestion_id"]
            params = {k: suggestion["parameter_values"][k] for k in PARAM_NAMES}
            eval_result = evaluate_candidate(params)
            attempted += 1
            row = make_row(attempted, suggestion_id, params, eval_result)

            if eval_result["status"] == "success":
                idem_key = client.make_idempotency_key("ackley6d-submit", campaign_id, suggestion_id)
                submit = client.submit_results(
                    campaign_id,
                    results=[{
                        "suggestion_id": suggestion_id,
                        "parameter_values": params,
                        "objective_values": row["objective_values"],
                    }],
                    idempotency_key=idem_key,
                )
                if not submit.get("success"):
                    row["status"] = "failed"
                    row["failure_reason"] = f"submit_rejected: {submit.get('errors')}"
                    print(f"[ALERT] result submission rejected for {suggestion_id}: {submit.get('errors')}")
                else:
                    print(f"[EVENT] eval#{attempted} success surface_response={eval_result['surface_response']:.6f}")
            else:
                try:
                    client.update_suggestion_status(suggestion_id, "rejected")
                except Exception as exc:
                    print(f"[ALERT] could not reject failed suggestion {suggestion_id}: {exc}")
                print(f"[ALERT] eval#{attempted} failed: {row.get('failure_reason')}")

            append_row(jsonl_path, csv_path, row)

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_s:
                print(f"[HEARTBEAT] attempted={attempted}/{TOTAL_BUDGET}")
                last_heartbeat = now

        print(f"[HEARTBEAT] attempted={attempted}/{TOTAL_BUDGET}")
        last_heartbeat = time.monotonic()

    rows = load_rows(jsonl_path)
    summary = summarize(rows)
    print_summary(summary, campaign_id)

    if attempted >= TOTAL_BUDGET:
        print(f"[EVENT] budget of {TOTAL_BUDGET} attempted evaluations reached")
    _pause_if_running(client, campaign_id)
    print(f"[EVENT] campaign_id={campaign_id} paused (or already terminal); rerun with --campaign-id {campaign_id} to resume")
    return campaign_id


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    info = client.get_campaign(campaign_id)
    if info.get("status") == "running":
        client.lifecycle(campaign_id, action="pause")
