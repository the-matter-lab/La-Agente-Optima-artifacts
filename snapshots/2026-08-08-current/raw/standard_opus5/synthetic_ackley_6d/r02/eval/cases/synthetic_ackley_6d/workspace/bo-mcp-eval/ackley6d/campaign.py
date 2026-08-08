"""Orchestration: BO-MCP loop for the Ackley-6D synthetic surface."""

import json
import time

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from . import MARKER
from .harness import evaluate_candidate
from .intake import CAMPAIGN_NAME, build_intake
from .objective import OBJECTIVE_NAME, evaluate
from .reporting import append_row, emit, finalize, log, result_line, set_log_path
from .space import PARAM_NAMES

GENERATE_ACTION = "bo_generate_suggestions"


@dataclass
class Config:
    campaign_id: str | None = None
    max_attempts: int = 60
    init_size: int = 12
    batch_size: int = 4
    seed: int = 913_477
    acquisition: str = "expected_improvement"
    poll_s: float = 180.0
    heartbeat_s: float = 1800.0
    stop_file: Path = Path("STOP")
    artifacts_root: Path = Path("artifacts")


def _key(params: dict) -> tuple:
    return tuple(round(float(params[n]), 9) for n in PARAM_NAMES)


def _field(client: BoMcpClient, campaign_id: str, key: str) -> str:
    info = client.get_campaign(campaign_id)
    info = info.get("campaign") or info
    return str(info.get(key, ""))


def _resolve_campaign(client: BoMcpClient, cfg: Config) -> str:

    if cfg.campaign_id:
        name = _field(client, cfg.campaign_id, "name")
        if MARKER not in name:
            raise SystemExit(f"campaign {cfg.campaign_id} lacks marker {MARKER}: name={name!r}")
        status = _field(client, cfg.campaign_id, "status")

        emit("EVENT", f"reusing campaign {cfg.campaign_id} (status={status})")
        if status in ("paused", "completed"):
            action = "resume" if status == "paused" else "reopen"
            client.lifecycle(cfg.campaign_id, action=action)
            emit("EVENT", f"campaign lifecycle action={action} applied")
        return cfg.campaign_id

    intake = build_intake(
        seed=cfg.seed,
        batch_size=cfg.batch_size,
        init_size=cfg.init_size,
        acquisition=cfg.acquisition,
    )
    client.validate_intake(intake)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    created = client.create_campaign(
        intake, idempotency_key=BoMcpClient.make_idempotency_key("create", CAMPAIGN_NAME, stamp)
    )
    cid = created["campaign_id"]
    emit("EVENT", f"created campaign {cid} name={CAMPAIGN_NAME}")
    return cid


def run(cfg: Config) -> str:
    client = BoMcpClient.from_env()
    campaign_id = _resolve_campaign(client, cfg)

    artifacts = cfg.artifacts_root / f"{MARKER}_{campaign_id}"
    artifacts.mkdir(parents=True, exist_ok=True)
    set_log_path(artifacts / "run.log")
    results_path = artifacts / "results.jsonl"
    emit("EVENT", f"artifacts dir: {artifacts}")

    prior = client.get_results(campaign_id)
    seen = {_key(r["parameter_values"]) for r in prior if r.get("parameter_values")}
    rows: list[dict] = [
        {
            "evaluation_index": i + 1,
            "suggestion_id": r.get("suggestion_id"),
            "parameter_values": r["parameter_values"],
            "objective_values": r.get("objective_values"),
            "status": "success",
            "failure_reason": None,
            "raw_response": evaluate(r["parameter_values"])["raw_response"],
        }
        for i, r in enumerate(prior)
    ]
    attempted = len(rows)
    if attempted:
        emit("EVENT", f"campaign already holds {attempted} results; budget {cfg.max_attempts}")

    last_beat = time.monotonic()
    stopped = False
    while attempted < cfg.max_attempts:
        if cfg.stop_file.exists():
            cfg.stop_file.unlink()
            emit("EVENT", f"stop file {cfg.stop_file} found - shutting down cleanly")
            stopped = True
            break

        decision = client.next_action(campaign_id)
        action = decision.get("action")
        log(f"next_action -> {decision}")
        if action != GENERATE_ACTION:
            emit("ALERT", f"server action={action} ({decision.get('reason', 'no reason')}) - stopping")
            break

        size = min(cfg.init_size if attempted == 0 else cfg.batch_size, cfg.max_attempts - attempted)
        emit("EVENT", f"generating {size} suggestion(s) (attempted {attempted}/{cfg.max_attempts})")
        gen = client.generate_suggestions(campaign_id, batch_size=size)
        suggestions = gen.get("suggestions") or client.query_suggestions(
            campaign_id, status_filter="pending"
        )
        if not suggestions:
            emit("ALERT", f"no suggestions returned: {gen.get('errors')} - waiting {cfg.poll_s}s")
            time.sleep(cfg.poll_s)
            continue

        batch: list[dict] = []
        for suggestion in suggestions:
            if attempted >= cfg.max_attempts:
                break
            params = suggestion.get("parameter_values", {})
            if _key(params) in seen:
                client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                emit("ALERT", f"duplicate candidate rejected (suggestion {suggestion['suggestion_id']})")
                continue
            seen.add(_key(params))
            attempted += 1
            row = evaluate_candidate(
                evaluate,
                evaluation_index=attempted,
                suggestion=suggestion,
                objective_name=OBJECTIVE_NAME,
            )
            rows.append(row)
            append_row(results_path, row)
            emit("RESULT", result_line(row))
            if row["status"] == "success":
                batch.append(
                    {
                        "suggestion_id": row["suggestion_id"],
                        "parameter_values": {n: float(params[n]) for n in PARAM_NAMES},
                        "objective_values": row["objective_values"],
                        "metadata": {"experiment_id": f"eval-{row['evaluation_index']:03d}"},
                    }
                )
            else:
                emit("ALERT", f"evaluation #{row['evaluation_index']} failed: {row['failure_reason']}")
                client.update_suggestion_status(row["suggestion_id"], "failed")

        if batch:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            client.submit_results(
                campaign_id,
                results=batch,
                idempotency_key=BoMcpClient.make_idempotency_key("submit", campaign_id, stamp),
            )
            emit("EVENT", f"submitted {len(batch)} result(s); total attempted={attempted}")

        if time.monotonic() - last_beat >= cfg.heartbeat_s:
            last_beat = time.monotonic()
            emit("HEARTBEAT", f"alive - attempted {attempted}/{cfg.max_attempts}")

    if attempted >= cfg.max_attempts:
        emit("EVENT", f"budget reached: {attempted}/{cfg.max_attempts} attempted evaluations")

    summary = finalize(artifacts, campaign_id, rows, attempted)
    log(f"summary={summary}")

    try:
        diag = client.get_diagnostics(campaign_id, timeout_s=900.0)
        (artifacts / "diagnostics.json").write_text(json.dumps(diag, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001 - diagnostics are advisory
        emit("ALERT", f"diagnostics unavailable: {type(exc).__name__}: {exc}")

    status = _field(client, campaign_id, "status")

    if status == "running":
        client.lifecycle(campaign_id, action="pause")
        emit("EVENT", "campaign paused (resume by re-running with --campaign-id)")
    else:
        emit("EVENT", f"campaign status={status}; no pause needed")
    if stopped:
        emit("EVENT", "stopped on request")

    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
    return campaign_id
