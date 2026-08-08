"""Campaign orchestration: BO-MCP loop, oracle evaluation, reporting."""

import time
from dataclasses import dataclass
from pathlib import Path

import logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from . import intake as intake_module
from . import oracle, reporting, search_space

NAME = search_space.OBJECTIVE_NAME
GENERATE_ACTION = "bo_generate_suggestions"
SUBMIT_ACTION = "bo_submit_results"


@dataclass
class Config:
    campaign_id: str | None = None
    total_budget: int = 60
    max_attempts: int = 60
    poll_s: float = 180.0
    heartbeat_s: float = 1800.0
    oracle_timeout_s: float = 120.0
    stop_file: Path = Path("STOP")
    artifacts_dir: Path = Path("artifacts")


def run(cfg: Config) -> dict:
    run_dir = cfg.artifacts_dir / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir.mkdir(parents=True, exist_ok=True)
    runlog, jsonl = run_dir / "run.log", run_dir / "attempts.jsonl"

    def emit(tag: str, message: str) -> None:
        print(f"[{tag}] {message}", flush=True)
        reporting.log(runlog, f"{tag}: {message}")
        logfire.info("{tag}: {message}", tag=tag, message=message)

    def detail(message: str) -> None:
        reporting.log(runlog, f"detail: {message}")
        logfire.debug("{message}", message=message)

    client = BoMcpClient.from_env(timeout_s=300.0)
    campaign_id = cfg.campaign_id or _create(client, emit)
    _ensure_running(client, campaign_id, emit)
    emit("EVENT", f"campaign {campaign_id} | artifacts {run_dir}")

    attempts_this_run = 0
    last_beat = time.monotonic()

    while True:
        if cfg.stop_file.exists():
            emit("EVENT", f"stop file {cfg.stop_file} found -> shutting down")
            cfg.stop_file.unlink(missing_ok=True)
            break

        rows, failures = _server_state(client, campaign_id)
        attempted = len(rows) + len(failures)
        if attempted >= cfg.total_budget:
            emit("ALERT", f"campaign budget reached: {attempted}/{cfg.total_budget} attempts")
            break
        if attempts_this_run >= cfg.max_attempts:
            emit("EVENT", f"invocation budget reached: {attempts_this_run} attempts")
            break

        decision = client.next_action(campaign_id)
        detail(f"next_action={decision}")
        action = decision.get("action")
        if action == SUBMIT_ACTION:  # an earlier run generated but never reported
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            suggestion = pending[0] if pending else None
        elif action == GENERATE_ACTION:
            suggestion = _next_suggestion(client, campaign_id, cfg.poll_s, detail)
        else:
            emit("ALERT", f"server stops the loop: {action} ({decision.get('reason')})")
            break
        if suggestion is None:
            emit("ALERT", f"no suggestion available from BO-MCP (action={action}) -> shutting down")
            break

        candidate = search_space.canonicalize(suggestion.get("parameter_values") or {})
        outcome = oracle.evaluate(
            candidate, objective_name=NAME, timeout_s=cfg.oracle_timeout_s
        )
        attempts_this_run += 1
        attempt_no = attempted + 1
        reporting.append_jsonl(
            jsonl, {"attempt": attempt_no, "candidate": candidate, **outcome}
        )

        if outcome["status"] == "success":
            _submit(client, campaign_id, suggestion.get("suggestion_id"), candidate, outcome["value"])
            best = max([r["value"] for r in rows] + [outcome["value"]])
            emit(
                "RESULT",
                f"attempt {attempt_no}/{cfg.total_budget} | {NAME}={outcome['value']:.2f} percent "
                f"| best={best:.2f} | {reporting.fmt_candidate(candidate)}",
            )
        else:
            _reject(client, suggestion.get("suggestion_id"), detail)
            emit(
                "ALERT",
                f"attempt {attempt_no}/{cfg.total_budget} FAILED ({outcome['error'][:160]}) "
                f"| {reporting.fmt_candidate(candidate)}",
            )

        if time.monotonic() - last_beat >= cfg.heartbeat_s:
            last_beat = time.monotonic()
            emit("HEARTBEAT", f"alive | {attempts_this_run} attempts this invocation")

    return _finalize(client, campaign_id, run_dir, emit, detail)


def _create(client: BoMcpClient, emit) -> str:
    payload = intake_module.build_intake()
    client.validate_intake(payload)
    response = client.create_campaign(
        payload, idempotency_key=client.make_idempotency_key("da-yield-create", payload["name"])
    )
    campaign_id = response["campaign_id"]
    emit("EVENT", f"created BayBE campaign '{payload['name']}' -> {campaign_id}")
    return campaign_id


def _ensure_running(client: BoMcpClient, campaign_id: str, emit) -> None:
    status = client.next_action(campaign_id).get("status")
    action = {"paused": "resume", "completed": "reopen"}.get(str(status))
    if action:
        client.lifecycle(campaign_id, action=action)
        emit("EVENT", f"campaign was {status} -> {action}d")


def _server_state(client: BoMcpClient, campaign_id: str) -> tuple[list[dict], list[dict]]:
    rows = reporting.result_rows(client.get_results(campaign_id), NAME)
    failures = reporting.failed_rows(
        client.query_suggestions(campaign_id, status_filter="rejected")
    )
    return rows, failures


def _next_suggestion(client: BoMcpClient, campaign_id: str, poll_s: float, detail) -> dict | None:
    try:
        response = client.generate_suggestions(campaign_id, batch_size=1)
        suggestions = list(response.get("suggestions") or [])
    except (BoMcpClientError, BoMcpOperationError) as exc:
        detail(f"generate_suggestions failed ({exc}); re-querying pending")
        time.sleep(min(poll_s, 30.0))
        suggestions = []
    if not suggestions:
        suggestions = client.query_suggestions(campaign_id, status_filter="pending")
    return suggestions[0] if suggestions else None


def _submit(client: BoMcpClient, campaign_id: str, suggestion_id, candidate, value) -> None:
    row = {
        "parameter_values": candidate,
        "objective_values": {NAME: value},
        "suggestion_id": suggestion_id,
    }
    key = client.make_idempotency_key("da-yield-result", campaign_id, str(suggestion_id))
    try:
        client.submit_results(campaign_id, results=[row], idempotency_key=key)
    except BoMcpOperationError:
        client.submit_results(
            campaign_id,
            results=[row],
            idempotency_key=client.make_idempotency_key("da-yield-force", campaign_id, str(suggestion_id)),
            force=True,
        )


def _reject(client: BoMcpClient, suggestion_id, detail) -> None:
    """Retire a suggestion whose oracle call failed; the attempt still counts."""
    if not suggestion_id:
        return
    try:
        client.update_suggestion_status(suggestion_id, "rejected")
    except (BoMcpClientError, BoMcpOperationError) as exc:
        detail(f"could not mark suggestion {suggestion_id} rejected: {exc}")


def _finalize(client: BoMcpClient, campaign_id: str, run_dir: Path, emit, detail) -> dict:
    rows, failures = _server_state(client, campaign_id)
    report = reporting.build_report(rows, failures, NAME)
    report["campaign_id"] = campaign_id
    reporting.print_report(report, emit)
    path = reporting.write_report(run_dir, report)
    if str(client.next_action(campaign_id).get("status")) == "running":
        try:
            client.lifecycle(campaign_id, action="pause")
            emit("EVENT", f"campaign {campaign_id} paused (resume with --campaign-id {campaign_id})")
        except (BoMcpClientError, BoMcpOperationError) as exc:
            detail(f"pause failed: {exc}")
    emit("EVENT", f"report written to {path}")
    return report
