"""Thin BO-MCP orchestration for the direct arylation benchmark."""

import json
import time
import uuid
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate_candidate
from .intake import CACHE_BUSTER_NONCE, OWNERSHIP_MARKER, build_intake
from .reporting import append_jsonl, build_report, utc_now, write_report

ARTIFACT_ROOT = Path("artifacts/direct_arylation_bo")
_RUN_LOG: Path | None = None


def emit(tag: str, message: str) -> None:
    line = f"[{tag}] {message}"
    print(line, flush=True)
    if _RUN_LOG is not None:
        with _RUN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _campaign_attempts(suggestions: list[dict]) -> int:
    return sum(row.get("status") in {"completed", "rejected"} for row in suggestions)


def _verify_ownership(campaign: dict) -> None:
    if OWNERSHIP_MARKER not in campaign.get("name", ""):
        raise RuntimeError(
            "Refusing campaign without required ownership marker " + OWNERSHIP_MARKER
        )


def _activate_campaign(client: BoMcpClient, campaign_id: str) -> None:
    campaign = client.get_campaign(campaign_id)
    _verify_ownership(campaign)
    status = campaign.get("status")
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        emit("EVENT", f"Resumed campaign {campaign_id}")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        emit("EVENT", f"Reopened campaign {campaign_id}")
    elif status in {"terminated", "failed"}:
        raise RuntimeError(f"Campaign {campaign_id} cannot continue from status {status}")


def _create_or_resume(
    client: BoMcpClient, *, campaign_id: str | None, smoke_test: bool
) -> str:
    if campaign_id:
        _activate_campaign(client, campaign_id)
        return campaign_id

    intake = build_intake(smoke_test=smoke_test)
    client.validate_intake(intake)
    key_suffix = "smoke" if smoke_test else "live"
    response = client.create_campaign(
        intake,
        idempotency_key=f"direct-arylation-{OWNERSHIP_MARKER}-{key_suffix}",
    )
    new_id = response["campaign_id"]
    _verify_ownership(client.get_campaign(new_id))
    return new_id


def _submit_success(
    client: BoMcpClient,
    *,
    campaign_id: str,
    suggestion: dict,
    value: float,
    poll_s: float,
) -> None:
    row = {
        "suggestion_id": suggestion["suggestion_id"],
        "parameter_values": suggestion["parameter_values"],
        "objective_values": {"yield": value},
        "metadata": {
            "experiment_id": suggestion["suggestion_id"],
            "notes": f"direct arylation oracle; nonce={CACHE_BUSTER_NONCE}",
        },
    }
    key_material = json.dumps(row, sort_keys=True)
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{campaign_id}:{key_material}"))
    for attempt in range(3):
        try:
            client.submit_results(
                campaign_id,
                results=[row],
                idempotency_key=key,
                force=True,
            )
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(min(poll_s, 5.0))


def _reject_failure(
    client: BoMcpClient, *, suggestion_id: str, poll_s: float
) -> None:
    for attempt in range(3):
        try:
            client.update_suggestion_status(suggestion_id, "rejected")
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(min(poll_s, 5.0))


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    status = client.get_campaign(campaign_id).get("status")
    if status in {"running", "active"}:
        client.lifecycle(campaign_id, action="pause")
        emit("EVENT", f"Paused campaign {campaign_id}")


def run_campaign(
    *,
    campaign_id: str | None,
    poll_s: float,
    heartbeat_s: float,
    stop_file: Path,
    oracle_timeout_s: float,
    smoke_test: bool,
) -> str:
    target_attempts = 1 if smoke_test else 60
    client = BoMcpClient.from_env(timeout_s=max(120.0, poll_s))
    campaign_id = _create_or_resume(
        client, campaign_id=campaign_id, smoke_test=smoke_test
    )
    artifact_dir = ARTIFACT_ROOT / campaign_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    global _RUN_LOG
    _RUN_LOG = artifact_dir / "run.log"
    (artifact_dir / "campaign_id.txt").write_text(campaign_id + "\n", encoding="utf-8")
    emit("EVENT", f"CAMPAIGN_ID={campaign_id}")
    emit("EVENT", f"ARTIFACT_DIR={artifact_dir}")
    logfire.info(
        "direct arylation campaign active",
        campaign_id=campaign_id,
        target_attempts=target_attempts,
        nonce=CACHE_BUSTER_NONCE,
    )

    last_heartbeat = time.monotonic()
    try:
        while True:
            suggestions = client.query_suggestions(campaign_id, limit=500)
            attempted = _campaign_attempts(suggestions)
            if attempted > target_attempts:
                raise RuntimeError(
                    f"Campaign already has {attempted} attempts; budget is {target_attempts}"
                )
            if attempted == target_attempts:
                emit("EVENT", f"Attempt budget reached: {attempted}/{target_attempts}")
                break

            if stop_file.exists():
                stop_file.unlink()
                emit("EVENT", f"Stop file consumed: {stop_file}")
                break

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_s:
                emit(
                    "HEARTBEAT",
                    f"campaign={campaign_id} attempts={attempted}/{target_attempts}",
                )
                last_heartbeat = now

            pending = client.query_suggestions(
                campaign_id, status_filter="pending", limit=500
            )
            if pending:
                suggestion = pending[0]
                emit("EVENT", f"Reusing pending suggestion {suggestion['suggestion_id']}")
            else:
                decision = client.next_action(campaign_id)
                if decision.get("action") != "bo_generate_suggestions":
                    emit("ALERT", f"BO-MCP stop decision: {decision}")
                    break
                generated = client.generate_suggestions(
                    campaign_id,
                    batch_size=1,
                    timeout_s=max(900.0, poll_s * 3),
                )
                suggestion = generated["suggestions"][0]
                emit("EVENT", f"Generated suggestion {suggestion['suggestion_id']}")

            params: dict[str, Any] = suggestion["parameter_values"]
            outcome = evaluate_candidate(params, timeout_s=oracle_timeout_s)
            record = {
                "timestamp": utc_now(),
                "campaign_id": campaign_id,
                "suggestion_id": suggestion["suggestion_id"],
                "parameter_values": params,
                **outcome,
            }
            append_jsonl(artifact_dir / "attempts.jsonl", record)

            if outcome["status"] == "successful":
                _submit_success(
                    client,
                    campaign_id=campaign_id,
                    suggestion=suggestion,
                    value=outcome["yield"],
                    poll_s=poll_s,
                )
                emit("RESULT", json.dumps(record, sort_keys=True))
            else:
                _reject_failure(
                    client,
                    suggestion_id=suggestion["suggestion_id"],
                    poll_s=poll_s,
                )
                emit("ALERT", json.dumps(record, sort_keys=True))
                emit("RESULT", json.dumps(record, sort_keys=True))
    finally:
        suggestions = client.query_suggestions(campaign_id, limit=500)
        results = client.get_results(campaign_id)
        report = build_report(
            campaign_id=campaign_id, suggestions=suggestions, results=results
        )
        write_report(artifact_dir, report)
        emit(
            "RESULT",
            json.dumps(
                {
                    "campaign_id": campaign_id,
                    "attempted_evaluations": report["attempted_evaluations"],
                    "successful_evaluations": report["successful_evaluations"],
                    "best_measured_yield": report["best_measured_yield"],
                    "best_reaction_conditions": report["best_reaction_conditions"],
                    "report_path": str(artifact_dir / "final_report.json"),
                },
                sort_keys=True,
            ),
        )
        _pause_if_running(client, campaign_id)
    return campaign_id
