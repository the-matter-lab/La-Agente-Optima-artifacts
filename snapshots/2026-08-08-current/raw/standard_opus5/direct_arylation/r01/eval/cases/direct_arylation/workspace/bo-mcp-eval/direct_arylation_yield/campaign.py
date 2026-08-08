"""Orchestration: BO-MCP loop for the direct arylation yield campaign."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from . import evaluation, intake, reporting
from . import search_space as ss
from .reporting import say

log = logging.getLogger("direct_arylation_yield")

_ACTION_CONTINUE = "bo_generate_suggestions"


def _ensure_campaign(client: BoMcpClient, campaign_id: str | None, spec: dict) -> str:
    if campaign_id:
        say("EVENT", f"reusing campaign {campaign_id}")
        return campaign_id
    response = client.create_campaign(
        spec, idempotency_key=BoMcpClient.make_idempotency_key("create", intake.CAMPAIGN_NAME)
    )
    new_id = response["campaign_id"]
    say("EVENT", f"created campaign {new_id} ({intake.CAMPAIGN_NAME})")
    return new_id


def _make_runnable(client: BoMcpClient, campaign_id: str) -> dict:
    """Resume a paused / reopen a completed campaign, then re-read the decision."""
    decision = client.next_action(campaign_id)
    action = {"paused": "resume", "completed": "reopen"}.get(decision.get("status"))
    if action:
        say("EVENT", f"campaign is {decision['status']}; sending lifecycle action '{action}'")
        client.lifecycle(campaign_id, action=action)
        decision = client.next_action(campaign_id)
    return decision


def _pending_suggestions(client: BoMcpClient, campaign_id: str, batch_size: int) -> list[dict]:
    existing = client.query_suggestions(campaign_id, status_filter="pending")
    if existing:
        return existing
    try:
        generated = client.generate_suggestions(campaign_id, batch_size=batch_size)
        return generated.get("suggestions") or []
    except Exception as exc:  # a read timeout does not prove nothing was produced
        log.warning("generate_suggestions raised %s; re-querying pending", exc)
        return client.query_suggestions(campaign_id, status_filter="pending")


def run(
    *,
    campaign_id: str | None = None,
    max_attempts: int = 60,
    batch_size: int = 1,
    initial_design_size: int = 6,
    random_seed: int = 2805,
    poll_s: float = 180.0,
    heartbeat_s: float = 1800.0,
    stop_file: Path = Path("STOP"),
    artifacts_root: Path = Path("artifacts"),
    eval_timeout_s: float = 120.0,
) -> dict:
    oracle_url = os.environ.get("DIRECT_ARYLATION_API_URL")
    if not oracle_url:
        raise SystemExit("DIRECT_ARYLATION_API_URL is not set; it must point at the oracle service.")

    client = BoMcpClient.from_env()
    spec = intake.build_intake(
        batch_size=batch_size, initial_design_size=initial_design_size, random_seed=random_seed
    )
    campaign_id = _ensure_campaign(client, campaign_id, spec)
    artifacts = reporting.Artifacts(artifacts_root, campaign_id)
    say("EVENT", f"budget={max_attempts} attempted evaluations | artifacts={artifacts.dir}")

    attempts = 0
    best = max(
        (r.get("objective_values", {}).get(ss.OBJECTIVE_NAME) for r in client.get_results(campaign_id)),
        default=None,
    )
    last_beat = time.monotonic()

    while attempts < max_attempts:
        if stop_file.exists():
            say("EVENT", f"stop file {stop_file} found — shutting down after {attempts} attempts")
            stop_file.unlink(missing_ok=True)
            break

        decision = _make_runnable(client, campaign_id)
        if decision.get("action") != _ACTION_CONTINUE:
            say("ALERT", f"server stops the loop: action={decision.get('action')} reason={decision.get('reason')}")
            break

        wanted = min(batch_size, max_attempts - attempts)
        suggestions = _pending_suggestions(client, campaign_id, wanted)
        if not suggestions:
            say("ALERT", f"no suggestions available; retrying in {poll_s:.0f}s")
            time.sleep(poll_s)
            continue

        for suggestion in suggestions:
            if attempts >= max_attempts:
                break
            values = ss.canonical_parameter_values(suggestion["parameter_values"])
            outcome = evaluation.evaluate(
                oracle_url, values, objective_name=ss.OBJECTIVE_NAME, timeout_s=eval_timeout_s
            )
            attempts += 1
            record = reporting.make_record(
                attempt=attempts,
                campaign_id=campaign_id,
                nonce=intake.NONCE,
                suggestion_id=suggestion.get("suggestion_id"),
                parameter_values=values,
                objective_name=ss.OBJECTIVE_NAME,
                status=outcome.status,
                objective_value=outcome.objective_value,
                detail=outcome.detail,
            )
            artifacts.add(record)

            # Submit before any pause: BO-MCP rejects results on a non-running campaign.
            if outcome.ok:
                client.submit_results(
                    campaign_id,
                    results=[
                        {
                            "suggestion_id": record["suggestion_id"],
                            "parameter_values": values,
                            "objective_values": record["objective_values"],
                        }
                    ],
                    idempotency_key=BoMcpClient.make_idempotency_key(
                        "result", campaign_id, str(record["suggestion_id"]), record["attempted_at"]
                    ),
                    force=True,
                )
                best = outcome.objective_value if best is None else max(best, outcome.objective_value)
            else:
                # Retire the unexecutable suggestion without penalising its coordinates.
                client.update_suggestion_status(record["suggestion_id"], "rejected")
            reporting.announce_result(
                record,
                objective_name=ss.OBJECTIVE_NAME,
                unit=ss.OBJECTIVE_UNIT,
                budget=max_attempts,
                best=best,
            )

        if time.monotonic() - last_beat >= heartbeat_s:
            last_beat = time.monotonic()
            say("HEARTBEAT", f"alive — {attempts}/{max_attempts} attempts done on {campaign_id}")

    if attempts >= max_attempts:
        say("EVENT", f"invocation budget of {max_attempts} attempted evaluations exhausted")

    status = client.next_action(campaign_id).get("status")
    if status == "running":
        client.lifecycle(campaign_id, action="pause")
        say("EVENT", f"campaign {campaign_id} paused (resume with --campaign-id {campaign_id})")

    report = reporting.build_report(
        campaign_id=campaign_id,
        campaign_name=intake.CAMPAIGN_NAME,
        nonce=intake.NONCE,
        objective_name=ss.OBJECTIVE_NAME,
        unit=ss.OBJECTIVE_UNIT,
        server_results=client.get_results(campaign_id),
        records=artifacts.records,
        all_records=artifacts.all_records,
        budget=max_attempts,
    )
    reporting.announce_report(report, artifacts)
    return report
