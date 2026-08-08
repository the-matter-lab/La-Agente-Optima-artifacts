import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError

from .evaluator import evaluate_candidate
from .intake import CAMPAIGN_NAME, MARKER, NONCE, TOTAL_ATTEMPTS, build_intake
from .reporting import append_jsonl, load_attempts, write_reports
from .search_space import build_parameters


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tag(tag: str, message: str) -> None:
    line = f"[{tag}] {message}"
    logging.info(line)
    print(line, flush=True)


def _configure_file_log(artifact_dir: Path) -> None:
    logging.basicConfig(
        filename=artifact_dir / "run.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )


def _get_config(client: BoMcpClient, campaign_id: str) -> dict:
    return client._json_request("GET", f"/api/v1/campaigns/{campaign_id}/config")


def _assert_owned(campaign: dict, config: dict) -> None:
    if MARKER not in campaign.get("name", ""):
        raise RuntimeError(f"Refusing campaign without required marker {MARKER}")
    if campaign.get("name") != CAMPAIGN_NAME:
        raise RuntimeError("Campaign name does not exactly match this benchmark's owned name")
    if config.get("backend_requested") != "baybe" or config.get("backend_resolved") != "baybe":
        raise RuntimeError("Campaign is not pinned to and resolved as BayBE")
    if config.get("max_iterations") != TOTAL_ATTEMPTS or config.get("batch_size") != 1:
        raise RuntimeError("Campaign budget/batch configuration is not exactly 60 x 1")
    objectives = config.get("objectives") or []
    if len(objectives) != 1 or objectives[0].get("name") != "yield":
        raise RuntimeError("Campaign objective is not exactly yield")
    direction = objectives[0].get("direction") or objectives[0].get("target_mode")
    if direction != "maximize" or objectives[0].get("unit") != "percent":
        raise RuntimeError("Campaign objective direction/unit mismatch")
    expected = {row["name"]: row for row in build_parameters()}
    actual = {row["name"]: row for row in config.get("parameters") or []}
    if set(actual) != set(expected):
        raise RuntimeError("Campaign parameter names do not match the fixed search space")
    for name, wanted in expected.items():
        got = actual[name]
        values_key = "categories" if wanted["type"] == "categorical" else "values"
        if got.get("type") != wanted["type"] or got.get(values_key) != wanted[values_key]:
            raise RuntimeError(f"Campaign parameter mismatch for {name}")


def _open_campaign(client: BoMcpClient, campaign_id: str | None, artifact_dir: Path) -> tuple[dict, dict]:
    id_path = artifact_dir / "campaign_id.txt"
    if campaign_id is None and id_path.exists():
        campaign_id = id_path.read_text(encoding="utf-8").strip()
    if campaign_id:
        campaign = client.get_campaign(campaign_id)
        config = _get_config(client, campaign_id)
        _assert_owned(campaign, config)
        if campaign["status"] == "paused":
            client.lifecycle(campaign_id, action="resume")
            campaign = client.get_campaign(campaign_id)
            _tag("EVENT", f"resumed campaign {campaign_id}")
        elif campaign["status"] == "completed":
            if len(client.query_suggestions(campaign_id, limit=500)) < TOTAL_ATTEMPTS:
                client.lifecycle(campaign_id, action="reopen")
                campaign = client.get_campaign(campaign_id)
                _tag("EVENT", f"reopened campaign {campaign_id}")
        elif campaign["status"] != "running":
            raise RuntimeError(f"Refusing campaign in status {campaign['status']}")
        return campaign, config

    intake = build_intake()
    client.validate_intake(intake)
    created = client.create_campaign(
        intake,
        idempotency_key=client.make_idempotency_key("create", MARKER, NONCE),
    )
    campaign_id = created["campaign_id"]
    campaign = client.get_campaign(campaign_id)
    config = _get_config(client, campaign_id)
    _assert_owned(campaign, config)
    id_path.write_text(campaign_id + "\n", encoding="utf-8")
    _tag("EVENT", f"created campaign {campaign_id} name={CAMPAIGN_NAME} backend=baybe")
    return campaign, config


def run_campaign(
    *,
    campaign_id: str | None,
    artifact_dir: Path,
    invocation_attempt_budget: int,
    poll_s: int,
    heartbeat_s: int,
    stop_file: Path,
    oracle_timeout_s: float,
) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _configure_file_log(artifact_dir)
    client = BoMcpClient.from_env(timeout_s=120)
    campaign, config = _open_campaign(client, campaign_id, artifact_dir)
    campaign_id = campaign["id"]
    (artifact_dir / "campaign_metadata.json").write_text(
        json.dumps({"campaign": campaign, "config": config, "nonce": NONCE}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _tag("EVENT", f"campaign={campaign_id} marker={MARKER} nonce={NONCE}")
    invocation_attempts = 0
    last_heartbeat = time.monotonic()

    try:
        while invocation_attempts < invocation_attempt_budget:
            if stop_file.exists():
                _tag("EVENT", f"stop file detected at {stop_file}; removing marker and stopping normally")
                stop_file.unlink()
                break
            if time.monotonic() - last_heartbeat >= heartbeat_s:
                _tag("HEARTBEAT", f"campaign={campaign_id} invocation_attempts={invocation_attempts}")
                last_heartbeat = time.monotonic()

            suggestions = client.query_suggestions(campaign_id, limit=500)
            if len(suggestions) > TOTAL_ATTEMPTS:
                raise RuntimeError("Campaign has more than 60 suggestions; refusing to query oracle")
            pending = [row for row in suggestions if row.get("status") == "pending"]
            if not pending:
                if len(suggestions) >= TOTAL_ATTEMPTS:
                    _tag("EVENT", "exact 60-suggestion campaign budget reached")
                    break
                decision = client.next_action(campaign_id)
                if decision.get("action") != "bo_generate_suggestions":
                    _tag("ALERT", f"BO-MCP stopped before 60 attempts: {decision}")
                    break
                try:
                    generated = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=900)
                    pending = generated["suggestions"]
                except BoMcpClientError:
                    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
                    if not pending:
                        raise
            if len(pending) != 1:
                raise RuntimeError(f"Expected exactly one pending suggestion, found {len(pending)}")

            suggestion = pending[0]
            parameters = suggestion["parameter_values"]
            suggestion_id = suggestion["suggestion_id"]
            evaluation = evaluate_candidate(parameters, oracle_timeout_s)
            invocation_attempts += 1
            attempt_number = len(load_attempts(artifact_dir / "attempts.jsonl")) + 1
            record = {
                "attempt_number": attempt_number,
                "attempted_at_utc": _utc_now(),
                "campaign_id": campaign_id,
                "campaign_name": CAMPAIGN_NAME,
                "required_marker": MARKER,
                "cache_buster_nonce": NONCE,
                "suggestion_id": suggestion_id,
                "parameter_values": parameters,
                "status": evaluation.status,
                "objective_name": "yield",
                "objective_value": evaluation.objective_value,
                "objective_units": "percent",
                "http_status": evaluation.http_status,
                "error": evaluation.error,
                "response_excerpt": evaluation.response_excerpt,
            }
            append_jsonl(artifact_dir / "attempts.jsonl", record)
            if evaluation.status == "success":
                result = {
                    "suggestion_id": suggestion_id,
                    "parameter_values": parameters,
                    "objective_values": {"yield": evaluation.objective_value},
                    "metadata": {"notes": f"Direct arylation oracle; nonce={NONCE}"},
                }
                client.submit_results(
                    campaign_id,
                    results=[result],
                    idempotency_key=client.make_idempotency_key("result", campaign_id, suggestion_id),
                )
                _tag("RESULT", json.dumps(record, sort_keys=True))
            else:
                client.update_suggestion_status(suggestion_id, "rejected")
                _tag("ALERT", json.dumps(record, sort_keys=True))
            logfire.info(
                "direct arylation attempt",
                campaign_id=campaign_id,
                suggestion_id=suggestion_id,
                status=evaluation.status,
            )
    finally:
        campaign = client.get_campaign(campaign_id)
        if campaign["status"] == "running":
            client.lifecycle(campaign_id, action="pause")
            campaign = client.get_campaign(campaign_id)
            _tag("EVENT", f"paused campaign {campaign_id}")

    bo_results = client.get_results(campaign_id)
    summary = write_reports(artifact_dir, campaign, config, bo_results)
    _tag(
        "EVENT",
        f"artifacts={artifact_dir} attempted={summary['attempted_evaluations']} "
        f"successful={summary['successful_evaluations']} status={campaign['status']}",
    )
    return summary
