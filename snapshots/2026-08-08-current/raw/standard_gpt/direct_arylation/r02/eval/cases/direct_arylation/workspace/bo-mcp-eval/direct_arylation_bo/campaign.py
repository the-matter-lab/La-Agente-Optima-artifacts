from __future__ import annotations

import contextlib
import io
import json
import time
from pathlib import Path
from typing import Any

import logfire
from grafico.core.logfire_config import configure_logfire

from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate_candidate
from .intake import build_intake, validate_space
from .reporting import append_jsonl, candidate_text, ensure_dir, read_attempts, utc_now, write_reports
from .search_space import ARTIFACT_ROOT, CAMPAIGN_NAME, MARKER, OBJECTIVE_NAME

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    configure_logfire(console=False)
logfire.instrument_requests()

_RUN_LOG_PATH: Path | None = None


def _event(tag: str, message: str) -> None:
    line = f"[{tag}] {message}"
    if _RUN_LOG_PATH is not None:
        with _RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    print(line, flush=True)


def _manifest_path() -> Path:
    return Path("campaign_manifest.json")


def _update_manifest(latest_artifact_dir: Path) -> None:
    payload = {
        "campaign_slug": "direct_arylation_bo",
        "marker": MARKER,
        "package_modules": [
            "direct_arylation_bo.search_space",
            "direct_arylation_bo.intake",
            "direct_arylation_bo.evaluator",
            "direct_arylation_bo.reporting",
            "direct_arylation_bo.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_bo.py",
        "latest_artifact_dir": str(latest_artifact_dir),
    }
    _manifest_path().write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ensure_campaign_owned(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    if MARKER not in campaign.get("name", ""):
        raise RuntimeError(
            f"Campaign {campaign_id} is not owned by this invocation because its name lacks marker {MARKER}"
        )
    return campaign


def _resume_if_needed(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    campaign = _ensure_campaign_owned(client, campaign_id)
    status = campaign.get("status", "")
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        _event("EVENT", f"resumed campaign_id={campaign_id}")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        _event("EVENT", f"reopened campaign_id={campaign_id}")
    elif status == "terminated":
        raise RuntimeError(f"Campaign {campaign_id} is terminated and must not be reused")
    return _ensure_campaign_owned(client, campaign_id)


def _prepare_artifact_dir(campaign_id: str) -> Path:
    global _RUN_LOG_PATH
    artifact_dir = ensure_dir(Path(ARTIFACT_ROOT) / campaign_id)
    _RUN_LOG_PATH = artifact_dir / "run.log"
    _update_manifest(artifact_dir)
    return artifact_dir


def _get_or_create_campaign(client: BoMcpClient, campaign_id: str | None) -> str:
    if campaign_id:
        return _resume_if_needed(client, campaign_id)["id"]

    intake = build_intake()
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"Campaign intake invalid: {validation.get('errors')}")
    create_key = client.make_idempotency_key("create", CAMPAIGN_NAME, MARKER)
    created = client.create_campaign(intake, idempotency_key=create_key)
    new_campaign_id = created.get("campaign_id")
    if not new_campaign_id:
        raise RuntimeError(f"Campaign creation failed: {created}")
    owned = _ensure_campaign_owned(client, new_campaign_id)
    _event("EVENT", f"created campaign_id={new_campaign_id} name={owned['name']}")
    return new_campaign_id


def _next_pending_or_generate(client: BoMcpClient, campaign_id: str) -> dict[str, Any] | None:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=1)
    if pending:
        return pending[0]

    decision = client.next_action(campaign_id)
    action = decision.get("action", "")
    if action != "bo_generate_suggestions":
        return {"_decision_only": True, "action": action, "detail": decision}

    generated = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=900.0)
    suggestions = generated.get("suggestions", [])
    if suggestions:
        return suggestions[0]
    return {"_decision_only": True, "action": "no_suggestions", "detail": generated}


def _submission_payload(suggestion: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "suggestion_id": suggestion["suggestion_id"],
        "parameter_values": attempt["candidate"],
        "objective_values": {OBJECTIVE_NAME: attempt[OBJECTIVE_NAME]},
        "metadata": {
            "batch_ref": f"attempt-{attempt['attempt_index']}",
            "notes": f"ownership marker {MARKER}",
        },
    }


def _emit_attempt(attempt: dict[str, Any], max_attempts: int) -> None:
    base = (
        f"attempt={attempt['attempt_index']}/{max_attempts} status={attempt['status']} "
        f"campaign_id={attempt['campaign_id']} suggestion_id={attempt['suggestion_id']} "
        f"conditions=({candidate_text(attempt['candidate'])})"
    )
    if attempt["status"] == "success":
        _event("RESULT", f"{base} yield={attempt[OBJECTIVE_NAME]:.4f}")
    else:
        _event("ALERT", f"{base} error={attempt.get('error', 'unknown')}")


def _maybe_heartbeat(last_heartbeat: float, heartbeat_s: int, attempted: int, max_attempts: int, campaign_id: str) -> float:
    now = time.time()
    if now - last_heartbeat >= heartbeat_s:
        _event("HEARTBEAT", f"campaign_id={campaign_id} attempted={attempted}/{max_attempts} marker={MARKER}")
        return now
    return last_heartbeat


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    campaign = client.get_campaign(campaign_id)
    status = campaign.get("status")
    if status == "running":
        client.lifecycle(campaign_id, action="pause")
        _event("EVENT", f"paused campaign_id={campaign_id}")
    else:
        _event("EVENT", f"leaving campaign_id={campaign_id} status={status}")


def run_campaign(*, campaign_id: str | None, max_attempts: int, oracle_timeout_s: float, poll_s: int, heartbeat_s: int, stop_file: str, validate_only: bool) -> dict[str, Any]:
    validate_space()
    ensure_dir(ARTIFACT_ROOT)
    client = BoMcpClient.from_env(timeout_s=120.0)
    _event("EVENT", f"starting run validate_only={str(validate_only).lower()} marker={MARKER}")

    intake = build_intake()
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"Campaign intake invalid: {validation.get('errors')}")
    _event("EVENT", "validated BO-MCP intake")
    if validate_only:
        return {"validated": True}

    campaign_id = _get_or_create_campaign(client, campaign_id)
    artifact_dir = _prepare_artifact_dir(campaign_id)
    log_path = artifact_dir / "run.log"
    attempts_path = artifact_dir / "attempts.jsonl"
    existing_attempts = read_attempts(attempts_path)
    attempted = len(existing_attempts)
    successes = sum(1 for item in existing_attempts if item.get("status") == "success")
    _event(
        "EVENT",
        f"campaign_id={campaign_id} artifact_dir={artifact_dir} prior_attempts={attempted} prior_successes={successes}",
    )
    if attempted >= max_attempts:
        _event("EVENT", f"attempt budget already exhausted at {attempted}/{max_attempts}")

    last_heartbeat = 0.0
    stop_path = Path(stop_file)

    while attempted < max_attempts:
        last_heartbeat = _maybe_heartbeat(last_heartbeat, heartbeat_s, attempted, max_attempts, campaign_id)
        if stop_path.exists():
            stop_path.unlink()
            _event("EVENT", f"stop file detected and cleared at {stop_path}")
            break

        item = _next_pending_or_generate(client, campaign_id)
        if not item:
            _event("ALERT", "no suggestion or decision available")
            break
        if item.get("_decision_only"):
            action = item.get("action", "")
            if action in {"completed", "terminated", "stopped", "budget_exhausted", "no_suggestions"}:
                _event("EVENT", f"next_action={action}; stopping invocation")
                break
            _event("EVENT", f"next_action={action}; sleeping {poll_s}s")
            time.sleep(poll_s)
            continue

        attempt_index = attempted + 1
        suggestion_id = item["suggestion_id"]
        candidate = item["parameter_values"]
        _event("EVENT", f"evaluating attempt={attempt_index}/{max_attempts} suggestion_id={suggestion_id}")
        outcome = evaluate_candidate(candidate, timeout_s=oracle_timeout_s)
        attempt_record = {
            **outcome,
            "attempt_index": attempt_index,
            "campaign_id": campaign_id,
            "created_at": utc_now(),
            "suggestion_id": suggestion_id,
        }

        if outcome["status"] == "success":
            submit_key = client.make_idempotency_key("submit", campaign_id, str(attempt_index), suggestion_id)
            response = client.submit_results(
                campaign_id,
                results=[_submission_payload(item, attempt_record)],
                idempotency_key=submit_key,
                force=True,
            )
            attempt_record["result_ids"] = response.get("result_ids", [])
        else:
            client.update_suggestion_status(suggestion_id, "rejected")

        append_jsonl(attempts_path, attempt_record)
        attempted += 1
        if attempt_record["status"] == "success":
            successes += 1
        _emit_attempt(attempt_record, max_attempts)

    diagnostics = None
    if successes:
        try:
            diagnostics = client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=600.0)
        except Exception as exc:  # pragma: no cover - best effort only
            _event("ALERT", f"diagnostics_unavailable error={exc}")
            if _RUN_LOG_PATH is not None:
                with _RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(f"[DEBUG] diagnostics_unavailable error={exc}\n")

    attempts = read_attempts(attempts_path)
    report_paths = write_reports(
        artifact_dir=artifact_dir,
        campaign_id=campaign_id,
        attempts=attempts,
        diagnostics=diagnostics,
    )
    best = max((item for item in attempts if item.get("status") == "success"), key=lambda item: item[OBJECTIVE_NAME], default=None)
    if best is None:
        _event("RESULT", f"best_yield=n/a attempted={len(attempts)} successful={successes}")
    else:
        _event(
            "RESULT",
            f"best_yield={best[OBJECTIVE_NAME]:.4f} attempted={len(attempts)} successful={successes} conditions=({candidate_text(best['candidate'])})",
        )
    _event("RESULT", f"campaign_id={campaign_id} summary_json={report_paths['summary_json']} report_md={report_paths['report_md']}")
    _pause_if_running(client, campaign_id)
    return {
        "campaign_id": campaign_id,
        "artifact_dir": str(artifact_dir),
        "attempts_path": str(attempts_path),
        "log_path": str(log_path),
        **report_paths,
    }
