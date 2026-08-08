"""BO-MCP orchestration loop for the Ackley benchmark.

Owns the campaign lifecycle: create (or resume/reopen), iterate via
``next_action``, evaluate candidates, submit results, and pause at
shutdown.  Never persists loop state to disk — the server is the
single source of truth.
"""

import os
import sys
import time
import uuid
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .evaluator import evaluate
from .reporter import (
    emit_alert,
    emit_event,
    emit_heartbeat,
    emit_result,
    init_artifact_dir,
    log_result,
)
from .search_space import build_intake


def run(
    *,
    client: BoMcpClient,
    campaign_id: str | None,
    max_evaluations: int,
    artifact_dir: str,
    poll_s: int,
    heartbeat_s: int,
    stop_file: str,
) -> str:
    """Execute the BO campaign loop.

    Parameters
    ----------
    client : BoMcpClient
        Authenticated client.
    campaign_id : str or None
        Existing campaign to resume/reopen, or ``None`` to create a new one.
    max_evaluations : int
        Hard cap on attempted evaluations for this invocation.
    artifact_dir : str
        Directory for append-only JSONL artifact.
    poll_s : int
        Seconds between ``next_action`` polls when the server says wait.
    heartbeat_s : int
        Seconds between liveness heartbeats.
    stop_file : str
        Path to a stop-marker file; checked at the top of each iteration.

    Returns
    -------
    str
        The campaign_id (new or resumed).
    """
    init_artifact_dir(artifact_dir)

    # ── campaign lifecycle ─────────────────────────────────────────
    if campaign_id:
        # Resume or reopen an existing campaign
        campaign = client.get_campaign(campaign_id)
        status = campaign.get("status", "unknown")
        emit_event(f"found campaign {campaign_id} status={status}")
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            emit_event(f"resumed campaign {campaign_id}")
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            emit_event(f"reopened campaign {campaign_id}")
        elif status == "running":
            emit_event(f"campaign {campaign_id} already running")
        else:
            emit_alert(f"campaign {campaign_id} status={status} — cannot run")
            sys.exit(1)
    else:
        intake = build_intake()
        # Validate first
        try:
            client.validate_intake(intake)
        except BoMcpOperationError as exc:
            emit_alert(f"intake validation failed: {exc.payload}")
            sys.exit(1)
        # Create
        idem_key = client.make_idempotency_key("ackley-create")
        resp = client.create_campaign(intake, idempotency_key=idem_key)
        if not resp.get("success"):
            emit_alert(f"campaign creation rejected: {resp}")
            sys.exit(1)
        campaign_id = resp["campaign_id"]
        emit_event(f"created campaign {campaign_id}")

    # ── main loop ──────────────────────────────────────────────────
    evaluation_count = 0
    last_heartbeat = time.monotonic()
    # param_tuple → cached result row (for duplicate force-submission)
    seen_params: dict[tuple[float, ...], dict[str, Any]] = {}
    # Per-point force-submission counter to prevent secondary stall
    _force_submit_counts: dict[tuple[float, ...], int] = {}
    _MAX_FORCE_SUBMITS_PER_POINT = 5
    _consecutive_gen_failures = 0
    _MAX_CONSECUTIVE_GEN_FAILURES = 10

    # Seed seen_params from existing campaign results so resume/reopen
    # does not re-evaluate points the server already knows about.
    _seed_seen_params_from_server(client, campaign_id, seen_params)
    if seen_params:
        emit_event(f"seeded dedup cache with {len(seen_params)} prior results")

    while evaluation_count < max_evaluations:
        # Stop-file check
        if os.path.exists(stop_file):
            emit_event("stop file detected — shutting down")
            os.remove(stop_file)
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            emit_heartbeat(
                f"campaign={campaign_id} evals={evaluation_count}/{max_evaluations}"
            )
            last_heartbeat = now

        # Ask server what to do (informational — we drive toward the budget)
        decision = client.next_action(campaign_id)
        action = decision.get("action")

        if action == "wait":
            emit_event(
                f"server says wait (reason={decision.get('reason')}) "
                f"— polling in {poll_s}s"
            )
            time.sleep(poll_s)
            continue

        if action != "bo_generate_suggestions":
            emit_event(
                f"server action={action} reason={decision.get('reason')} "
                f"iteration={decision.get('iteration')} "
                f"n_results={decision.get('n_results')} "
                f"— ignoring, budget remains {evaluation_count}/{max_evaluations}"
            )
            # Fall through — still try to generate; the server may still
            # produce suggestions for a running campaign.

        # Generate a suggestion (with retry on transient failures)
        gen_resp = None
        for _retry in range(3):
            try:
                gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
                break
            except BoMcpOperationError as exc:
                emit_alert(
                    f"suggestion generation rejected (retry {_retry + 1}/3): "
                    f"{exc.payload}"
                )
                time.sleep(5.0)
        else:
            _consecutive_gen_failures += 1
            emit_alert(
                f"generation failed after 3 retries "
                f"(consecutive={_consecutive_gen_failures}/"
                f"{_MAX_CONSECUTIVE_GEN_FAILURES})"
            )
            if _consecutive_gen_failures >= _MAX_CONSECUTIVE_GEN_FAILURES:
                emit_alert("too many consecutive generation failures — aborting")
                break
            time.sleep(poll_s)
            continue

        _consecutive_gen_failures = 0  # reset on success

        if not gen_resp.get("success"):
            emit_alert(
                f"suggestion generation returned success=false: "
                f"{gen_resp.get('errors')} — retrying"
            )
            time.sleep(poll_s)
            continue

        suggestions = gen_resp.get("suggestions", [])
        if not suggestions:
            emit_event("no suggestions returned — retrying after poll")
            time.sleep(poll_s)
            continue

        suggestion = suggestions[0]
        suggestion_id = suggestion["suggestion_id"]
        params = suggestion["parameter_values"]

        # Deduplication: if we've already evaluated this exact point,
        # force-submit the cached result instead of re-evaluating.
        param_tuple = tuple(
            params.get(f"x_{i}", float("nan")) for i in range(1, 7)
        )
        if param_tuple in seen_params:
            fc = _force_submit_counts.get(param_tuple, 0) + 1
            _force_submit_counts[param_tuple] = fc
            if fc > _MAX_FORCE_SUBMITS_PER_POINT:
                emit_alert(
                    f"duplicate point force-submitted {fc - 1} times — "
                    f"backend keeps re-suggesting it; aborting to avoid stall"
                )
                break

            cached = seen_params[param_tuple]
            emit_event(
                f"duplicate suggestion (already eval #{cached['eval_index']}) — "
                f"force-submitting cached result (attempt {fc})"
            )
            _force_submit_cached(
                client,
                campaign_id,
                suggestion_id,
                cached,
                force_submit_index=fc,
            )
            continue

        # Evaluate
        evaluation_count += 1
        row = evaluate(params)
        row["suggestion_id"] = suggestion_id
        row["eval_index"] = evaluation_count

        # Cache for potential future duplicate force-submissions
        seen_params[param_tuple] = row

        emit_result(
            evaluation_count,
            params,
            row["objective_values"].get("surface_response"),
            row.get("raw_response"),
            row["status"],
        )
        log_result(artifact_dir, row, evaluation_count)

        # Submit result
        if row["status"] == "success":
            result_payload = {
                "suggestion_id": suggestion_id,
                "parameter_values": params,
                "objective_values": row["objective_values"],
            }
        else:
            # Failed evaluation — reject the suggestion
            client.update_suggestion_status(suggestion_id, "rejected")
            emit_alert(
                f"eval {evaluation_count} failed: {row['failure_reason']} — "
                f"suggestion {suggestion_id} rejected"
            )
            continue

        idem_key = client.make_idempotency_key(
            "ackley-result", str(evaluation_count)
        )
        try:
            submit_resp = client.submit_results(
                campaign_id,
                results=[result_payload],
                idempotency_key=idem_key,
            )
        except BoMcpOperationError as exc:
            # If the server rejected as duplicate, retry with force.
            if _is_duplicate_rejection(exc.payload):
                emit_event(
                    f"eval {evaluation_count} rejected as server-side "
                    f"duplicate — retrying with force=True"
                )
                submit_resp = _submit_with_force(
                    client, campaign_id, result_payload, evaluation_count
                )
                if not submit_resp.get("success"):
                    emit_alert(
                        f"force-submit also failed: "
                        f"{submit_resp.get('errors')}"
                    )
            else:
                emit_alert(f"result submission rejected: {exc.payload}")
            continue

        if not submit_resp.get("success"):
            if _is_duplicate_rejection(submit_resp):
                emit_event(
                    f"eval {evaluation_count} rejected as server-side "
                    f"duplicate — retrying with force=True"
                )
                submit_resp = _submit_with_force(
                    client, campaign_id, result_payload, evaluation_count
                )
                if not submit_resp.get("success"):
                    emit_alert(
                        f"force-submit also failed: "
                        f"{submit_resp.get('errors')}"
                    )
            else:
                emit_alert(
                    f"result submission failed: {submit_resp.get('errors')} "
                    f"field_errors={submit_resp.get('field_errors')}"
                )
            continue

    # ── shutdown ───────────────────────────────────────────────────
    emit_event(f"loop finished — {evaluation_count} evaluations attempted")

    # Pause the campaign (don't terminate — allows resume)
    try:
        campaign_status = client.get_campaign(campaign_id).get("status", "unknown")
        if campaign_status == "running":
            client.lifecycle(campaign_id, action="pause")
            emit_event(f"paused campaign {campaign_id}")
    except Exception as exc:
        emit_alert(f"pause failed (campaign left running): {exc}")

    return campaign_id


# ── helpers ──────────────────────────────────────────────────────────


def _param_tuple_from_result(result: dict[str, Any]) -> tuple[float, ...]:
    """Extract the (x_1, …, x_6) tuple from a server result row."""
    pv = result.get("parameter_values", {})
    return tuple(pv.get(f"x_{i}", float("nan")) for i in range(1, 7))


def _seed_seen_params_from_server(
    client: BoMcpClient,
    campaign_id: str,
    seen_params: dict[tuple[float, ...], dict[str, Any]],
) -> None:
    """Populate ``seen_params`` from the campaign's existing results."""
    try:
        results = client.get_results(campaign_id)
    except Exception:
        return
    for i, r in enumerate(results, start=1):
        pt = _param_tuple_from_result(r)
        if pt not in seen_params:
            seen_params[pt] = {
                "parameter_values": r.get("parameter_values", {}),
                "objective_values": r.get("objective_values", {}),
                "eval_index": i,
                "status": "success",
            }


def _is_duplicate_rejection(payload: dict[str, Any]) -> bool:
    """Return True if the payload indicates a duplicate-result rejection."""
    return payload.get("error_code") == "E004"


def _submit_with_force(
    client: BoMcpClient,
    campaign_id: str,
    result_payload: dict[str, Any],
    eval_index: int,
) -> dict[str, Any]:
    """Retry a submission with ``force=True`` under a fresh idempotency key."""
    idem_key = client.make_idempotency_key(
        "ackley-force-retry", str(eval_index)
    )
    try:
        return client.submit_results(
            campaign_id,
            results=[result_payload],
            idempotency_key=idem_key,
            force=True,
        )
    except BoMcpOperationError as exc:
        emit_alert(f"force-submit rejected: {exc.payload}")
        return {"success": False, "errors": [str(exc)]}


def _force_submit_cached(
    client: BoMcpClient,
    campaign_id: str,
    suggestion_id: str,
    cached: dict[str, Any],
    force_submit_index: int,
) -> None:
    """Submit a previously-evaluated result with ``force=True``.

    Does NOT count toward the evaluation budget — the point was already
    evaluated.  Uses a fresh idempotency key each time so the server
    processes every force-submission.
    """
    idem_key = client.make_idempotency_key(
        "ackley-force", str(force_submit_index), suggestion_id[:8]
    )
    try:
        submit_resp = client.submit_results(
            campaign_id,
            results=[
                {
                    "suggestion_id": suggestion_id,
                    "parameter_values": cached["parameter_values"],
                    "objective_values": cached["objective_values"],
                }
            ],
            idempotency_key=idem_key,
            force=True,
        )
        if not submit_resp.get("success"):
            emit_alert(
                f"force-submit failed: {submit_resp.get('errors')} "
                f"field_errors={submit_resp.get('field_errors')}"
            )
    except BoMcpOperationError as exc:
        emit_alert(f"force-submit rejected: {exc.payload}")