"""Campaign orchestration: create/resume, BO loop, oracle evaluation, reporting."""
from __future__ import annotations

import os
import time

import requests
import logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .oracle import evaluate_candidate
from .reporting import append_attempt_jsonl, build_final_report
from .search_space import build_intake


def _event(msg: str) -> None:
    print(f"[EVENT] {msg}", flush=True)


def _alert(msg: str) -> None:
    print(f"[ALERT] {msg}", flush=True)


def _result(msg: str) -> None:
    print(f"[RESULT] {msg}", flush=True)


def _heartbeat(msg: str) -> None:
    print(f"[HEARTBEAT] {msg}", flush=True)


def get_or_create_campaign(client: BoMcpClient, campaign_id: str | None, nonce: str) -> str:
    if campaign_id:
        camp = client.get_campaign(campaign_id)
        status = camp.get("status")
        if status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _event(f"reopened completed campaign {campaign_id}")
        elif status == "paused":
            client.lifecycle(campaign_id, action="resume")
            _event(f"resumed paused campaign {campaign_id}")
        elif status == "running":
            _event(f"continuing running campaign {campaign_id}")
        else:
            raise SystemExit(
                f"[ALERT] campaign {campaign_id} is in unrecoverable status '{status}'; not continuing"
            )
        return campaign_id

    intake = build_intake(nonce=nonce)
    client.validate_intake(intake)
    idem = BoMcpClient.make_idempotency_key("create", intake["name"])
    resp = client.create_campaign(intake, idempotency_key=idem)
    new_id = resp["campaign_id"]
    _event(f"created campaign {new_id} name={intake['name']}")
    return new_id


def _attempts_so_far(client: BoMcpClient, campaign_id: str) -> tuple[int, dict]:
    na = client.next_action(campaign_id)
    n_success = na.get("n_results") or 0
    rejected = client.query_suggestions(campaign_id, status_filter="rejected", limit=500)
    return n_success + len(rejected), na


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    camp = client.get_campaign(campaign_id)
    if camp.get("status") == "running":
        client.lifecycle(campaign_id, action="pause")
        _event(f"paused campaign {campaign_id}")


def _generate_one_suggestion(client: BoMcpClient, campaign_id: str, poll_s: float, heartbeat_s: float) -> dict:
    """Generate one suggestion; on a read timeout, re-query pending instead of
    blindly retrying (generation may have already succeeded server-side)."""
    try:
        gen = client.generate_suggestions(campaign_id, batch_size=1)
        return gen["suggestions"][0]
    except requests.exceptions.Timeout:
        _event("generate_suggestions timed out; polling for a pending suggestion instead of retrying")
        last_hb = time.monotonic()
        deadline = time.monotonic() + 30 * 60
        while time.monotonic() < deadline:
            time.sleep(poll_s)
            if time.monotonic() - last_hb >= heartbeat_s:
                _heartbeat("still waiting for suggestion generation to land")
                last_hb = time.monotonic()
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            if pending:
                return pending[0]
        raise RuntimeError("timed out waiting for a pending suggestion after generate_suggestions timeout")


def run(
    *,
    client: BoMcpClient,
    campaign_id: str,
    max_attempts: int,
    poll_s: float,
    heartbeat_s: float,
    stop_file: str,
    oracle_url: str,
    cache_buster: str,
) -> None:
    last_heartbeat = time.monotonic()
    while True:
        if os.path.exists(stop_file):
            _event(f"stop file '{stop_file}' found; deleting it and pausing campaign")
            os.remove(stop_file)
            _pause_if_running(client, campaign_id)
            break

        attempts_done, decision = _attempts_so_far(client, campaign_id)
        if attempts_done >= max_attempts:
            _event(f"attempt budget reached: {attempts_done}/{max_attempts}")
            _pause_if_running(client, campaign_id)
            break

        if decision.get("action") != "bo_generate_suggestions":
            _event(
                f"server recommends stopping: action={decision.get('action')} "
                f"reason={decision.get('reason')}"
            )
            _pause_if_running(client, campaign_id)
            break

        try:
            suggestion = _generate_one_suggestion(client, campaign_id, poll_s, heartbeat_s)
        except (BoMcpOperationError, RuntimeError) as exc:
            _alert(f"suggestion generation failed: {exc}")
            break

        params = suggestion["parameter_values"]
        outcome = evaluate_candidate(params, base_url=oracle_url, cache_buster=cache_buster)

        if outcome.ok:
            idem = BoMcpClient.make_idempotency_key("submit", campaign_id, suggestion["suggestion_id"])
            client.submit_results(
                campaign_id,
                results=[
                    {
                        "suggestion_id": suggestion["suggestion_id"],
                        "parameter_values": params,
                        "objective_values": {"yield": outcome.value},
                    }
                ],
                idempotency_key=idem,
            )
            append_attempt_jsonl(
                campaign_id,
                {"status": "success", "parameter_values": params, "yield": outcome.value},
            )
            _result(
                f"attempt {attempts_done + 1}/{max_attempts} success yield={outcome.value:.2f}% "
                f"conditions={params}"
            )
        else:
            client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
            append_attempt_jsonl(
                campaign_id,
                {"status": "failed", "parameter_values": params, "error": outcome.error},
            )
            _alert(
                f"attempt {attempts_done + 1}/{max_attempts} failed "
                f"http_status={outcome.http_status} error={outcome.error} conditions={params}"
            )

        if time.monotonic() - last_heartbeat >= heartbeat_s:
            _heartbeat(f"{attempts_done + 1}/{max_attempts} attempts completed so far")
            last_heartbeat = time.monotonic()


def finalize(client: BoMcpClient, campaign_id: str) -> None:
    report = build_final_report(client=client, campaign_id=campaign_id)
    _result(
        "campaign summary: "
        f"attempted={report['attempted_evaluations']} "
        f"successful={report['successful_evaluations']} "
        f"failed={report['failed_evaluations']}"
    )
    _result(
        f"best measured yield={report['best_measured_yield']} "
        f"conditions={report['best_conditions']}"
    )
    try:
        diag = client.get_diagnostics(campaign_id, verbosity="minimal", timeout_s=600.0)
        _result(f"diagnostics: {diag}")
    except Exception as exc:  # best-effort only, never fails the run
        logfire.debug("diagnostics call failed", error=str(exc))

    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
