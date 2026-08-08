"""Thin orchestration: BO-MCP loop over the Ackley-6 synthetic evaluator.

Crash/kill resilience contract:
* Pending suggestions left behind by a killed run are consumed before new ones
  are generated, so no evaluation slot is orphaned.
* Long blocking BO-MCP calls emit liveness ticks, so a monitor never sees a
  silent process.
* SIGINT/SIGTERM and any exception still run the shutdown path (artifacts +
  pause), and the stop file is only honoured at the top of an iteration.
"""

import concurrent.futures as cf
import signal
import time
from pathlib import Path

import logfire
import requests

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from . import intake as intake_mod
from . import report
from .harness import evaluate_candidates
from .objective import OBJECTIVE_NAME, evaluate
from .space import dedup_key

# Server recommendations that mean "there is still work to do this invocation".
WORK_ACTIONS = ("bo_generate_suggestions", "bo_submit_results")
# Any transport/operation failure that must not kill the loop.
CALL_ERRORS = (BoMcpClientError, BoMcpOperationError, requests.exceptions.RequestException)

_INTERRUPTED = {"flag": False}


def _install_signal_handlers() -> None:
    def handler(signum, _frame):
        _INTERRUPTED["flag"] = True
        print(f"[EVENT] signal {signum} received -> finishing current batch and shutting down", flush=True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def _await(call, label: str, tick_s: float):
    """Run a blocking BO-MCP call in a worker thread, printing liveness ticks."""
    with cf.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(call)
        waited = 0.0
        while True:
            try:
                return future.result(timeout=tick_s)
            except cf.TimeoutError:
                waited += tick_s
                print(f"[HEARTBEAT] {label}: still waiting after {waited:.0f}s", flush=True)


def _ensure_running(client: BoMcpClient, campaign_id: str, log) -> str:
    status = client.next_action(campaign_id)["status"]
    action = {"paused": "resume", "completed": "reopen"}.get(status)
    if action:
        client.lifecycle(campaign_id, action=action)
        print(f"[EVENT] campaign {status} -> {action}", flush=True)
        log(f"lifecycle {action} from status={status}")
    elif status not in ("running", "created"):
        print(f"[ALERT] campaign status={status} cannot be continued", flush=True)
    return status


def run(
    *,
    campaign_id: str | None,
    max_evals: int,
    poll_s: float,
    heartbeat_s: float,
    stop_file: str,
    artifact_base: str,
    eval_timeout_s: float,
    diagnostics_verbosity: str = "none",
) -> dict:
    artifact_dir = report.make_artifact_dir(artifact_base)
    log_path = artifact_dir / report.RUN_LOG
    tick_s = max(5.0, min(heartbeat_s, 60.0))  # liveness cadence inside blocking calls

    def log(message: str) -> None:
        with log_path.open("a") as fh:
            fh.write(f"{report.now()} {message}\n")
        logfire.debug("ackley6_bo: {message}", message=message)

    _install_signal_handlers()
    client = BoMcpClient.from_env(timeout_s=300.0)
    stop_path = Path(stop_file)

    if campaign_id is None:
        payload = intake_mod.build_intake()
        log(f"validate_intake -> {client.validate_intake(payload)}")
        created = client.create_campaign(
            payload,
            idempotency_key=BoMcpClient.make_idempotency_key("ackley6-create", intake_mod.CAMPAIGN_NAME),
        )
        campaign_id = created["campaign_id"]
        print(f"[EVENT] created campaign {campaign_id} ({intake_mod.CAMPAIGN_NAME})", flush=True)
    else:
        print(f"[EVENT] continuing campaign {campaign_id}", flush=True)
    _ensure_running(client, campaign_id, log)

    prior_results = client.next_action(campaign_id)["n_results"] or 0
    budget = max(0, max_evals - prior_results)
    print(
        f"[EVENT] budget: {max_evals} campaign-wide, {prior_results} already on server, "
        f"{budget} to evaluate now",
        flush=True,
    )
    log(f"campaign_id={campaign_id} campaign_budget={max_evals} prior={prior_results} budget={budget}")

    seen = {dedup_key(r["parameter_values"]) for r in client.get_results(campaign_id)}
    rows: list[dict] = []
    index = prior_results
    attempted = 0
    last_beat = time.monotonic()

    try:
        while attempted < budget:
            if _INTERRUPTED["flag"]:
                break
            if stop_path.exists():
                stop_path.unlink()
                print("[EVENT] stop file found -> shutting down", flush=True)
                log("stop file honoured")
                break

            decision = client.next_action(campaign_id)
            log(f"next_action -> {decision}")
            remaining = budget - attempted

            # Consume suggestions a previous (possibly killed) invocation left pending
            # before asking for new ones; this is also the server's 'bo_submit_results'
            # recommendation path.
            suggestions = client.query_suggestions(campaign_id, status_filter="pending")
            if suggestions:
                print(f"[EVENT] reusing {len(suggestions)} pending suggestion(s)", flush=True)
            elif decision["action"] in WORK_ACTIONS:
                batch = intake_mod.batch_size_for(decision.get("n_results") or 0, remaining)
                print(
                    f"[EVENT] iteration {decision['iteration']}: generating {batch} suggestion(s) "
                    f"({attempted}/{budget} evaluated this invocation)",
                    flush=True,
                )
                try:
                    response = _await(
                        lambda: client.generate_suggestions(campaign_id, batch_size=batch),
                        "suggestion generation",
                        tick_s,
                    )
                    suggestions = response.get("suggestions") or []
                except CALL_ERRORS as exc:
                    # A read timeout does not prove nothing was produced.
                    print(f"[ALERT] suggestion generation failed ({type(exc).__name__}), re-querying pending", flush=True)
                    log(f"generate failed: {exc}")
                    suggestions = client.query_suggestions(campaign_id, status_filter="pending")
            else:
                print(
                    f"[EVENT] server action={decision['action']} status={decision['status']} "
                    f"reason={decision['reason']} -> stopping",
                    flush=True,
                )
                break

            if not suggestions:
                print(f"[ALERT] no suggestions available, waiting {poll_s}s", flush=True)
                time.sleep(poll_s)
                suggestions = client.query_suggestions(campaign_id, status_filter="pending")
                if not suggestions:
                    print("[ALERT] still no suggestions -> stopping", flush=True)
                    break
            suggestions = suggestions[:remaining]

            candidates = []
            for suggestion in suggestions:
                key = dedup_key(suggestion["parameter_values"])
                if key in seen:
                    client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                    print(f"[ALERT] duplicate point rejected (not evaluated): {list(key)}", flush=True)
                    log(f"duplicate rejected suggestion={suggestion['suggestion_id']}")
                    continue
                seen.add(key)
                candidates.append(suggestion)
            if not candidates:
                continue

            evaluated = evaluate_candidates(
                candidates, evaluate, timeout_s=eval_timeout_s, max_workers=len(candidates)
            )
            attempted += len(evaluated)

            # Submit first, then honour any stop request: BO-MCP rejects results on a
            # non-running campaign, so results are never stranded.
            successes = [e for e in evaluated if e["status"] == "success"]
            submitted_ok = True
            if successes:
                try:
                    _await(
                        lambda: client.submit_results(
                            campaign_id,
                            results=[
                                {
                                    "suggestion_id": e["suggestion_id"],
                                    "parameter_values": e["parameter_values"],
                                    "objective_values": {OBJECTIVE_NAME: e["values"][OBJECTIVE_NAME]},
                                }
                                for e in successes
                            ],
                            idempotency_key=BoMcpClient.make_idempotency_key(
                                "ackley6-res", campaign_id, str(index)
                            ),
                        ),
                        "result submission",
                        tick_s,
                    )
                except CALL_ERRORS as exc:
                    submitted_ok = False
                    print(f"[ALERT] result submission rejected: {exc}", flush=True)
                    log(f"submit_results failed: {exc}")

            for item in evaluated:
                index += 1
                row = report.make_row(index, campaign_id, item, submitted_ok and item["status"] == "success")
                rows.append(row)
                report.append_row(artifact_dir, row)
                print(report.result_line(row, report.best_of(rows)), flush=True)
                if item["status"] != "success" and item["suggestion_id"]:
                    client.update_suggestion_status(item["suggestion_id"], "rejected")

            if time.monotonic() - last_beat > heartbeat_s:
                last_beat = time.monotonic()
                print(f"[HEARTBEAT] {attempted}/{budget} evaluations attempted this invocation", flush=True)
    except BaseException as exc:  # noqa: BLE001 - always finalize, then re-raise
        print(f"[ALERT] loop aborted: {type(exc).__name__}: {exc}", flush=True)
        log(f"loop aborted: {type(exc).__name__}: {exc}")
        _finalize(
            client, campaign_id, artifact_dir, artifact_base, rows, log, tick_s, diagnostics_verbosity
        )
        raise

    if budget == 0:
        print(f"[EVENT] campaign-wide budget of {max_evals} already satisfied; reporting only", flush=True)
    return _finalize(
        client, campaign_id, artifact_dir, artifact_base, rows, log, tick_s, diagnostics_verbosity
    )


def _finalize(
    client, campaign_id, artifact_dir, artifact_base, rows, log, tick_s: float = 30.0, verbosity: str = "none"
) -> dict:
    """Write the campaign-wide report and pause the campaign. Never raises."""
    diagnostics = None
    if verbosity != "none":
        print(f"[EVENT] finalizing: fetching BO-MCP diagnostics (verbosity={verbosity})", flush=True)
        try:
            diagnostics = _await(
                lambda: client.get_diagnostics(campaign_id, verbosity=verbosity, timeout_s=1800.0),
                "diagnostics",
                tick_s,
            )
        except CALL_ERRORS as exc:
            print(f"[ALERT] diagnostics unavailable: {exc}", flush=True)
            log(f"diagnostics failed: {exc}")

    try:
        all_rows = report.campaign_rows(client.get_results(campaign_id), artifact_base)
    except CALL_ERRORS as exc:
        print(f"[ALERT] could not read server results: {exc}", flush=True)
        all_rows = rows
    report.write_table(artifact_dir, all_rows)
    summary = report.write_final(artifact_dir, campaign_id, all_rows, diagnostics, len(rows))
    report.print_summary(summary, artifact_dir)

    try:
        if client.next_action(campaign_id)["status"] == "running":
            client.lifecycle(campaign_id, action="pause")
            print("[EVENT] campaign paused (resume with --campaign-id)", flush=True)
    except CALL_ERRORS as exc:
        print(f"[ALERT] could not pause campaign: {exc}", flush=True)
    return summary
