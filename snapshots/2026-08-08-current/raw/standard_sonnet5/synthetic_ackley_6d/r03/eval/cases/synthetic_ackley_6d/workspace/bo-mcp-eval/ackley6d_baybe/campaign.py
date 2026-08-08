"""Orchestrates the Ackley-6D BayBE campaign against BO-MCP.

Loop-state ownership: campaign progress (iteration/status/next action) is
always re-derived from the BO-MCP server via `next_action`/`get_results`,
never from a local counter. The one local file this module reads back
(`failed_evaluations.jsonl`) is *not* BO-progress bookkeeping -- BO-MCP has
no concept of a failed external evaluation (its result schema only accepts
finite objective values), so it is the only record of attempted-but-failed
points. It is required to enforce the fixed 60-attempt budget and to avoid
re-evaluating an already-attempted point; it is never used to decide
continue/stop, which remains `next_action`'s call.
"""
import os
import sys
import time

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .evaluate import evaluate_candidate
from .intake import BATCH_SIZE, OWNERSHIP_MARKER, build_intake
from .objective import OBJECTIVE_NAME
from .reporting import (
    append_failure_record,
    build_rows,
    load_failure_records,
    summarize,
    write_results_csv,
)
from .search_space import PARAMETER_NAMES

TOTAL_EVALUATION_BUDGET = 60


def _log(msg: str) -> None:
    print(msg, flush=True)


def _point_key(pv: dict) -> tuple:
    return tuple(round(float(pv[name]), 9) for name in PARAMETER_NAMES)


def _check_marker(name: str, campaign_id: str) -> None:
    if OWNERSHIP_MARKER not in name:
        _log(
            f"[ALERT] campaign {campaign_id} name '{name}' is missing required "
            f"ownership marker {OWNERSHIP_MARKER}; refusing to create/resume/report it"
        )
        sys.exit(1)


def create_or_resume(client: BoMcpClient, campaign_id: str | None) -> str:
    if campaign_id:
        campaign = client.get_campaign(campaign_id)
        _check_marker(campaign.get("name", ""), campaign_id)
        status = campaign.get("status")
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            _log(f"[EVENT] resumed paused campaign {campaign_id}")
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _log(f"[EVENT] reopened completed campaign {campaign_id}")
        else:
            _log(f"[EVENT] continuing campaign {campaign_id} (status={status})")
        return campaign_id

    intake = build_intake()
    assert OWNERSHIP_MARKER in intake["name"]
    validation = client.validate_intake(intake)
    if not validation.get("success", True):
        _log(f"[ALERT] intake validation rejected: {validation.get('errors')}")
        sys.exit(1)
    key = BoMcpClient.make_idempotency_key("ackley6d-baybe-create", OWNERSHIP_MARKER)
    response = client.create_campaign(intake, idempotency_key=key)
    if not response.get("success"):
        _log(f"[ALERT] campaign creation rejected: {response.get('errors')}")
        sys.exit(1)
    new_id = response["campaign_id"]
    _check_marker(intake["name"], new_id)
    _log(f"[EVENT] created campaign {new_id} name={intake['name']}")
    return new_id


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    campaign = client.get_campaign(campaign_id)
    if campaign.get("status") == "running":
        client.lifecycle(campaign_id, action="pause")
        _log(f"[EVENT] paused campaign {campaign_id}")


def run(
    client: BoMcpClient,
    campaign_id: str,
    artifact_dir: str,
    stop_file: str,
    heartbeat_s: float,
) -> dict:
    failures_path = os.path.join(artifact_dir, "failed_evaluations.jsonl")
    last_heartbeat = time.monotonic()

    while True:
        if time.monotonic() - last_heartbeat >= heartbeat_s:
            _log("[HEARTBEAT] campaign loop alive")
            last_heartbeat = time.monotonic()

        if os.path.exists(stop_file):
            _log(f"[EVENT] stop file '{stop_file}' detected; pausing and exiting")
            os.remove(stop_file)
            _pause_if_running(client, campaign_id)
            break

        server_results = client.get_results(campaign_id)
        failure_records = load_failure_records(failures_path)
        seen = {_point_key(r["parameter_values"]) for r in server_results}
        seen |= {_point_key(rec["parameter_values"]) for rec in failure_records}
        attempted = len(server_results) + len(failure_records)

        if attempted >= TOTAL_EVALUATION_BUDGET:
            _log(f"[EVENT] evaluation budget reached ({attempted}/{TOTAL_EVALUATION_BUDGET})")
            _pause_if_running(client, campaign_id)
            break

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            _log(
                f"[EVENT] server stop signal: action={decision.get('action')} "
                f"reason={decision.get('reason')}"
            )
            _pause_if_running(client, campaign_id)
            break

        remaining = TOTAL_EVALUATION_BUDGET - attempted
        batch_size = min(BATCH_SIZE, remaining)
        try:
            gen = client.generate_suggestions(campaign_id, batch_size=batch_size)
        except (BoMcpClientError, BoMcpOperationError) as exc:
            _log(f"[ALERT] suggestion generation failed: {exc}")
            break
        if not gen.get("success"):
            _log(f"[ALERT] suggestion generation rejected: {gen.get('errors')}")
            break

        suggestions = gen.get("suggestions", [])
        if not suggestions:
            _log("[ALERT] no suggestions returned; stopping")
            break

        results_payload = []
        for suggestion in suggestions:
            pv = suggestion["parameter_values"]
            sid = suggestion["suggestion_id"]
            key = _point_key(pv)
            if key in seen:
                client.update_suggestion_status(sid, "rejected")
                _log(f"[ALERT] duplicate candidate skipped (not evaluated): {pv}")
                continue
            seen.add(key)

            outcome = evaluate_candidate(pv)
            if outcome["status"] == "success":
                results_payload.append(
                    {
                        "parameter_values": pv,
                        "objective_values": outcome["objective_values"],
                        "suggestion_id": sid,
                    }
                )
                _log(
                    f"[RESULT] candidate={pv} raw_response={outcome['raw_response']:.6f} "
                    f"surface_response={outcome['objective_values'][OBJECTIVE_NAME]:.6f} "
                    "status=success"
                )
            else:
                client.update_suggestion_status(sid, "rejected")
                append_failure_record(
                    failures_path,
                    {
                        "parameter_values": pv,
                        "suggestion_id": sid,
                        "failure_reason": outcome["failure_reason"],
                    },
                )
                _log(
                    f"[ALERT] candidate evaluation failed: {pv} -> "
                    f"{outcome['failure_reason']}"
                )
                _log(f"[RESULT] candidate={pv} status=failed failure_reason={outcome['failure_reason']}")

        if results_payload:
            submit_key = BoMcpClient.make_idempotency_key(
                "ackley6d-baybe-submit", campaign_id, str(attempted)
            )
            submission = client.submit_results(
                campaign_id, results=results_payload, idempotency_key=submit_key
            )
            if not submission.get("success"):
                _log(f"[ALERT] result submission rejected: {submission.get('errors')}")

    return _final_report(client, campaign_id, artifact_dir, failures_path)


def _final_report(
    client: BoMcpClient, campaign_id: str, artifact_dir: str, failures_path: str
) -> dict:
    campaign = client.get_campaign(campaign_id)
    _check_marker(campaign.get("name", ""), campaign_id)

    server_results = client.get_results(campaign_id)
    failure_records = load_failure_records(failures_path)
    rows = build_rows(server_results, failure_records)
    csv_path = os.path.join(artifact_dir, "results.csv")
    write_results_csv(csv_path, rows)
    summary = summarize(rows)
    best = summary["best"]

    _log("[RESULT] ==== FINAL CAMPAIGN REPORT ====")
    _log(f"[RESULT] campaign_id={campaign_id}")
    _log(
        f"[RESULT] attempted_evaluations={summary['attempted']} "
        f"successful_evaluations={summary['successful']}"
    )
    if best:
        coords = {name: best[name] for name in PARAMETER_NAMES}
        _log(f"[RESULT] best_normalized_coordinates={coords}")
        _log(f"[RESULT] best_raw_response={best['raw_response']}")
        _log(f"[RESULT] best_surface_response={best['surface_response']}")
    else:
        _log("[ALERT] no successful evaluations recorded")
    _log(f"[RESULT] results_csv={csv_path}")
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
    return summary
