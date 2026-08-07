"""Thin BO-MCP orchestrator for the synthetic Ackley-6D benchmark.

Loop-state ownership stays with the BO-MCP server: continue/stop is derived
from ``next_action`` every iteration; nothing about campaign progress is
persisted to local disk. The CSV/JSONL artifacts are append-only provenance.
"""

import time
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from . import reporting
from .evaluation import run_candidate
from .intake import CAMPAIGN_NAME, OBJECTIVE_NAME, build_intake
from .objective import evaluate
from .search_space import PARAM_NAMES

TOTAL_BUDGET = 60  # exact attempted-evaluation budget for this benchmark


def _attempted_count(client: BoMcpClient, campaign_id: str) -> tuple[int, int]:
    """Return (successful, failed) counts derived from server state."""
    successful = len(client.get_results(campaign_id))
    failed = len(client.query_suggestions(campaign_id, status_filter="rejected"))
    return successful, failed


def _ensure_campaign(client: BoMcpClient, campaign_id: str | None, seed: int, batch_size: int, initial_design_size: int) -> str:
    if campaign_id:
        print(f"[EVENT] resuming campaign {campaign_id}", flush=True)
        info = client.get_campaign(campaign_id)
        if info.get("status") == "paused":
            client.lifecycle(campaign_id, action="resume")
            print(f"[EVENT] campaign {campaign_id} resumed (was paused)", flush=True)
        elif info.get("status") == "completed":
            client.lifecycle(campaign_id, action="reopen")
            print(f"[EVENT] campaign {campaign_id} reopened (was completed)", flush=True)
        return campaign_id

    intake = build_intake(seed=seed, batch_size=batch_size, initial_design_size=initial_design_size)
    idem_key = client.make_idempotency_key("ackley6d-bo-create", CAMPAIGN_NAME)
    resp = client.create_campaign(intake, idempotency_key=idem_key)
    if not resp.get("success"):
        raise RuntimeError(f"campaign creation rejected: {resp.get('errors')}")
    new_id = resp["campaign_id"]
    print(f"[EVENT] created campaign {new_id} name={CAMPAIGN_NAME}", flush=True)
    print(f"BO_MCP_CAMPAIGN_ID={new_id}", flush=True)
    return new_id


def _submit_success(client: BoMcpClient, campaign_id: str, suggestion: dict, outputs: dict) -> None:
    params = suggestion["parameter_values"]
    base_key = client.make_idempotency_key("ackley6d-bo-submit", suggestion["suggestion_id"])
    resp = client.submit_results(
        campaign_id,
        results=[
            {
                "parameter_values": params,
                "objective_values": {OBJECTIVE_NAME: outputs["surface_response"]},
                "suggestion_id": suggestion["suggestion_id"],
                "metadata": {"notes": f"raw_response={outputs['raw_response']!r}"},
            }
        ],
        idempotency_key=base_key,
    )
    if resp.get("success"):
        return
    # Replicate policy: do not reject solely for a duplicate-coordinate match; force it.
    force_key = client.make_idempotency_key("ackley6d-bo-submit-forced", suggestion["suggestion_id"])
    resp2 = client.submit_results(
        campaign_id,
        results=[
            {
                "parameter_values": params,
                "objective_values": {OBJECTIVE_NAME: outputs["surface_response"]},
                "suggestion_id": suggestion["suggestion_id"],
                "metadata": {"notes": f"raw_response={outputs['raw_response']!r}"},
            }
        ],
        idempotency_key=force_key,
        force=True,
    )
    if not resp2.get("success"):
        raise RuntimeError(f"result submission rejected twice: {resp.get('errors')} / {resp2.get('errors')}")


def run(
    campaign_id: str | None,
    seed: int,
    batch_size: int,
    initial_design_size: int,
    poll_s: float,
    heartbeat_s: float,
    stop_file: Path,
    artifact_dir: Path,
) -> None:
    client = BoMcpClient.from_env()
    campaign_id = _ensure_campaign(client, campaign_id, seed, batch_size, initial_design_size)
    csv_path, jsonl_path = reporting.artifact_paths(artifact_dir)

    last_heartbeat = time.monotonic()

    while True:
        if stop_file.exists():
            print(f"[EVENT] stop file {stop_file} found; honoring stop request", flush=True)
            stop_file.unlink()
            break

        successful, failed = _attempted_count(client, campaign_id)
        attempted = successful + failed
        if attempted >= TOTAL_BUDGET:
            print(f"[EVENT] attempted budget reached ({attempted}/{TOTAL_BUDGET})", flush=True)
            break

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            print(f"[EVENT] next_action={decision.get('action')} reason={decision.get('reason')!r}; stopping", flush=True)
            break

        remaining = TOTAL_BUDGET - attempted
        this_batch = max(1, min(batch_size, remaining))
        gen = client.generate_suggestions(campaign_id, batch_size=this_batch, timeout_s=poll_s)
        if not gen.get("success", True):
            print(f"[ALERT] suggestion generation failed: {gen.get('errors')}", flush=True)
            break
        suggestions = gen.get("suggestions", [])
        if not suggestions:
            print("[ALERT] no suggestions returned; stopping", flush=True)
            break

        for suggestion in suggestions:
            successful, failed = _attempted_count(client, campaign_id)
            attempted = successful + failed
            if attempted >= TOTAL_BUDGET:
                break

            outcome = run_candidate(evaluate, suggestion["parameter_values"])
            eval_index = attempted + 1

            if outcome["status"] == "success":
                outputs = outcome["outputs"]
                _submit_success(client, campaign_id, suggestion, outputs)
                row = {
                    "evaluation_index": eval_index,
                    "parameter_values": suggestion["parameter_values"],
                    "surface_response": outputs["surface_response"],
                    "raw_response": outputs["raw_response"],
                    "status": "success",
                    "failure_reason": None,
                }
            else:
                client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                row = {
                    "evaluation_index": eval_index,
                    "parameter_values": suggestion["parameter_values"],
                    "surface_response": None,
                    "raw_response": None,
                    "status": "failed",
                    "failure_reason": outcome["failure_reason"],
                }
                print(f"[ALERT] evaluation failed: {outcome['failure_reason']}", flush=True)

            reporting.append_row(csv_path, jsonl_path, row, PARAM_NAMES)
            reporting.print_result_line(row)

            if time.monotonic() - last_heartbeat >= heartbeat_s:
                print(f"[HEARTBEAT] campaign={campaign_id} attempted={eval_index}/{TOTAL_BUDGET}", flush=True)
                last_heartbeat = time.monotonic()

    info = client.get_campaign(campaign_id)
    if info.get("status") == "running":
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] campaign {campaign_id} paused", flush=True)

    successful, failed = _attempted_count(client, campaign_id)
    server_results = client.get_results(campaign_id)
    best = None
    for r in server_results:
        surface = r["objective_values"][OBJECTIVE_NAME]
        if best is None or surface > best["surface_response"]:
            raw = evaluate(r["parameter_values"])["raw_response"]
            best = {"parameter_values": r["parameter_values"], "surface_response": surface, "raw_response": raw}
    local_count = sum(1 for _ in open(jsonl_path)) if jsonl_path.exists() else 0
    attempted_total = successful + failed
    if local_count != attempted_total:
        print(
            f"[ALERT] local artifact row count ({local_count}) != server attempted count "
            f"({attempted_total}); run: uv run python recover_ackley6d_bo.py "
            f"--campaign-id {campaign_id} --artifact-dir {artifact_dir}",
            flush=True,
        )
    reporting.print_final_summary(campaign_id, attempted_total, successful, best)


