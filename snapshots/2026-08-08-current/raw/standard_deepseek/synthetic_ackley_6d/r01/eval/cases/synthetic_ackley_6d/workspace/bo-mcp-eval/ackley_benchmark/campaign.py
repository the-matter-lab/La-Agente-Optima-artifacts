"""Campaign orchestrator: loop, evaluate, submit, report.

Owns the BO-MCP lifecycle for the Ackley-6D benchmark.  Does **not**
import campaign-specific modules — the caller wires them in.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from domains.bo_mcp.client import BoMcpClient

# ── tagged-output helpers ──────────────────────────────────────────────


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def event(msg: str) -> None:
    _emit("EVENT", msg)


def alert(msg: str) -> None:
    _emit("ALERT", msg)


def result(msg: str) -> None:
    _emit("RESULT", msg)


def heartbeat(msg: str) -> None:
    _emit("HEARTBEAT", msg)


# ── helpers ────────────────────────────────────────────────────────────

# Precision for floating-point parameter comparison (≈ 1e-9 in normalised space).
_PARAM_ROUND = 12
_PARAM_NAMES = [f"x_{i}" for i in range(1, 7)]
# After this many consecutive duplicates, inject a random point.
_RANDOM_INJECT_AFTER_DUPES = 3


def _param_key(param_values: dict[str, float]) -> tuple[tuple[str, float], ...]:
    """Return a hashable, order-stable key for duplicate detection."""
    return tuple(
        (k, round(float(v), _PARAM_ROUND))
        for k, v in sorted(param_values.items())
    )


def _random_params(
    rng: random.Random, seen: set[tuple[tuple[str, float], ...]]
) -> dict[str, float]:
    """Draw a random point in [0,1]^6 not already in *seen*."""
    for _ in range(100):
        pv = {name: rng.random() for name in _PARAM_NAMES}
        if _param_key(pv) not in seen:
            return pv
    # Fallback (astronomically unlikely): perturb until unique.
    while True:
        pv = {name: rng.random() for name in _PARAM_NAMES}
        if _param_key(pv) not in seen:
            return pv


def _load_seen_keys_from_results(
    client: BoMcpClient, campaign_id: str
) -> set[tuple[tuple[str, float], ...]]:
    """Fetch existing results from BO-MCP and return their parameter keys."""
    seen: set[tuple[tuple[str, float], ...]] = set()
    try:
        rows = client.get_results(campaign_id)
        for row in rows:
            pv = row.get("parameter_values") or {}
            param_values = {k: float(v) for k, v in pv.items()}
            seen.add(_param_key(param_values))
    except Exception:
        pass  # best-effort; duplicates will be caught at submit time
    return seen


def _make_result_row(
    suggestion_id: str,
    parameter_values: dict[str, float],
    objective_values: dict[str, float],
) -> dict[str, object]:
    """Build a result dict for BO-MCP submission, omitting empty suggestion_id."""
    row: dict[str, object] = {
        "parameter_values": parameter_values,
        "objective_values": objective_values,
    }
    if suggestion_id:
        row["suggestion_id"] = suggestion_id
    return row


def _append_result_row(
    log_path: str,
    *,
    evaluation_index: int,
    parameter_values: dict[str, float],
    objective_values: dict[str, float] | None,
    status: str,
    failure_reason: str | None = None,
    raw_response: float | None = None,
) -> None:
    row: dict[str, object] = {
        "evaluation_index": evaluation_index,
        "parameter_values": parameter_values,
        "objective_values": objective_values,
        "status": status,
    }
    if failure_reason is not None:
        row["failure_reason"] = failure_reason
    if raw_response is not None:
        row["raw_response"] = raw_response
    with open(log_path, "a") as fh:
        fh.write(json.dumps(row) + "\n")


# ── orchestrator ───────────────────────────────────────────────────────


def run_campaign(
    *,
    client: BoMcpClient,
    intake: dict[str, object],
    evaluate: Callable[[dict[str, float]], dict[str, object]],
    extract_objective_values: Callable[[dict[str, object]], dict[str, float]],
    extract_raw_response: Callable[[dict[str, object]], float],
    max_evaluations: int,
    poll_s: float,
    heartbeat_s: float,
    stop_file: str | None,
    campaign_id: str | None,
    artifact_dir: str,
) -> str:
    """Execute the BO-MCP campaign loop.

    Returns the ``campaign_id``.
    """
    # ── create or resume ───────────────────────────────────────────
    if campaign_id is None:
        idem_key = BoMcpClient.make_idempotency_key("create", "ackley-6d")
        event(f"Creating campaign  idempotency_key={idem_key}")
        create_resp = client.create_campaign(intake, idempotency_key=idem_key)
        if not create_resp.get("success"):
            raise RuntimeError(f"Campaign creation rejected: {create_resp}")
        campaign_id = str(create_resp["campaign_id"])
        event(f"Created campaign_id={campaign_id}")
    else:
        event(f"Resuming campaign_id={campaign_id}")
        status_info = client.next_action(campaign_id)
        current_status = status_info.get("status", "unknown")
        event(f"Campaign status={current_status}  iteration={status_info.get('iteration')}  n_results={status_info.get('n_results')}")
        if current_status == "completed":
            alert("Campaign is completed — reopening")
            client.lifecycle(campaign_id, action="reopen")
            event("Reopened campaign")
        elif current_status == "paused":
            client.lifecycle(campaign_id, action="resume")
            event("Resumed campaign")

    # ── result log ─────────────────────────────────────────────────
    os.makedirs(artifact_dir, exist_ok=True)
    result_log = os.path.join(artifact_dir, "results.jsonl")
    event(f"Result log: {result_log}")

    # ── duplicate tracking ─────────────────────────────────────────
    seen_param_keys: set[tuple[tuple[str, float], ...]] = _load_seen_keys_from_results(
        client, campaign_id
    )
    event(f"Loaded {len(seen_param_keys)} existing result keys for duplicate detection")

    # ── loop ───────────────────────────────────────────────────────
    evaluation_index = 0
    last_heartbeat = time.monotonic()

    while evaluation_index < max_evaluations:
        # --- stop-file check ---------------------------------------
        if stop_file and os.path.exists(stop_file):
            event(f"Stop file '{stop_file}' detected — shutting down")
            os.remove(stop_file)
            break

        # --- heartbeat ---------------------------------------------
        now_m = time.monotonic()
        if now_m - last_heartbeat >= heartbeat_s:
            heartbeat(f"evaluation_index={evaluation_index}/{max_evaluations}  campaign_id={campaign_id}")
            last_heartbeat = now_m

        # --- next-action decision ----------------------------------
        decision = client.next_action(campaign_id)
        action = decision.get("action")
        event(
            f"next_action → action={action}  "
            f"iteration={decision.get('iteration')}  "
            f"n_results={decision.get('n_results')}  "
            f"status={decision.get('status')}"
        )

        if action == "bo_submit_results":
            # Pending suggestions exist (e.g. from a prior crash).
            # Query them, reject duplicates, submit non-duplicates.
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            event(
                f"Handling {len(pending)} pending suggestion(s) — "
                f"reason: {decision.get('reason', 'unknown')}"
            )
            for psug in pending:
                psug_id = psug["suggestion_id"]
                pv = {k: float(v) for k, v in (psug.get("parameter_values") or {}).items()}
                pk = _param_key(pv)
                if pk in seen_param_keys:
                    alert(
                        f"Rejecting pending duplicate: "
                        f"params={{{', '.join(f'{k}={v:.4f}' for k, v in pv.items())}}}"
                    )
                    try:
                        client.update_suggestion_status(psug_id, "rejected")
                    except Exception:
                        pass
                    continue
                # Not a duplicate — evaluate and submit.
                evaluation_index += 1
                seen_param_keys.add(pk)
                try:
                    eval_result = evaluate(pv)
                    status = str(eval_result.get("status", "success"))
                except Exception as exc:
                    eval_result = {"status": "failed", "error": str(exc)}
                    status = "failed"
                if status == "success":
                    obj_vals = extract_objective_values(eval_result)
                    raw_resp = extract_raw_response(eval_result)
                    idem_key = BoMcpClient.make_idempotency_key(
                        "submit", campaign_id, f"eval{evaluation_index}"
                    )
                    submit_resp = client.submit_results(
                        campaign_id,
                        results=[_make_result_row(psug_id, pv, obj_vals)],
                        idempotency_key=idem_key,
                    )
                    if submit_resp.get("success"):
                        result(
                            f"eval={evaluation_index}  "
                            f"surface_response={obj_vals['surface_response']:.6f}  "
                            f"raw_response={raw_resp:.6f}  "
                            f"params={{{', '.join(f'{k}={v:.4f}' for k, v in pv.items())}}}"
                        )
                        _append_result_row(
                            result_log,
                            evaluation_index=evaluation_index,
                            parameter_values=pv,
                            objective_values=obj_vals,
                            status="success",
                            raw_response=raw_resp,
                        )
                    else:
                        alert(
                            f"Submit rejected for eval {evaluation_index}: "
                            f"{submit_resp.get('errors')}"
                        )
                        _append_result_row(
                            result_log,
                            evaluation_index=evaluation_index,
                            parameter_values=pv,
                            objective_values=None,
                            status="submit_rejected",
                            failure_reason=str(submit_resp.get("errors", "")),
                            raw_response=raw_resp,
                        )
                else:
                    failure_reason = str(eval_result.get("error", "unknown"))
                    alert(f"eval={evaluation_index} FAILED: {failure_reason}")
                    try:
                        client.update_suggestion_status(psug_id, "rejected")
                    except Exception:
                        pass
                    _append_result_row(
                        result_log,
                        evaluation_index=evaluation_index,
                        parameter_values=pv,
                        objective_values=None,
                        status="failed",
                        failure_reason=failure_reason,
                    )
            time.sleep(poll_s)
            continue

        if action != "bo_generate_suggestions":
            reason = decision.get("reason", "no reason given")
            event(f"Server says stop: {reason}")
            break

        # --- generate + deduplicate (retry loop with random injection) ---
        consecutive_duplicates = 0
        rng = random.Random()
        while True:
            gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
            if not gen_resp.get("success"):
                errors = gen_resp.get("errors", [])
                alert(f"Suggestion generation failed: {errors}")
                break

            suggestions = gen_resp.get("suggestions") or []
            if not suggestions:
                alert("No suggestions returned — stopping")
                break

            sug = suggestions[0]
            suggestion_id = sug["suggestion_id"]
            param_values = {
                k: float(v) for k, v in sug["parameter_values"].items()
            }
            pkey = _param_key(param_values)

            if pkey in seen_param_keys:
                consecutive_duplicates += 1
                alert(
                    f"Duplicate suggestion detected (consecutive={consecutive_duplicates}): "
                    f"params={{{', '.join(f'{k}={v:.4f}' for k, v in param_values.items())}}}"
                )
                try:
                    client.update_suggestion_status(suggestion_id, "rejected")
                except Exception:
                    pass

                if consecutive_duplicates >= _RANDOM_INJECT_AFTER_DUPES:
                    # Inject a random point to break the BO model out of its local optimum.
                    event(
                        f"Injecting random point after {consecutive_duplicates} consecutive duplicates"
                    )
                    param_values = _random_params(rng, seen_param_keys)
                    pkey = _param_key(param_values)
                    suggestion_id = ""  # no BO-MCP suggestion for random points
                    consecutive_duplicates = 0
                    break  # proceed to evaluate the random point
                continue  # retry generation

            # Not a duplicate — proceed to evaluate.
            consecutive_duplicates = 0
            break

        # If the inner loop broke without a valid suggestion, exit outer loop.
        if not suggestions:
            break

        # --- evaluate ----------------------------------------------
        evaluation_index += 1
        seen_param_keys.add(pkey)
        try:
            eval_result = evaluate(param_values)
            status = str(eval_result.get("status", "success"))
        except Exception as exc:
            eval_result = {"status": "failed", "error": str(exc)}
            status = "failed"

        if status == "success":
            obj_vals = extract_objective_values(eval_result)
            raw_resp = extract_raw_response(eval_result)
            idem_key = BoMcpClient.make_idempotency_key(
                "submit", campaign_id, f"eval{evaluation_index}"
            )
            submit_resp = client.submit_results(
                campaign_id,
                results=[_make_result_row(suggestion_id, param_values, obj_vals)],
                idempotency_key=idem_key,
            )
            if not submit_resp.get("success"):
                alert(
                    f"Submit rejected for eval {evaluation_index}: "
                    f"{submit_resp.get('errors')}  "
                    f"field_errors={submit_resp.get('field_errors')}"
                )
                _append_result_row(
                    result_log,
                    evaluation_index=evaluation_index,
                    parameter_values=param_values,
                    objective_values=None,
                    status="submit_rejected",
                    failure_reason=str(submit_resp.get("errors", "")),
                    raw_response=raw_resp,
                )
            else:
                result(
                    f"eval={evaluation_index}  "
                    f"surface_response={obj_vals['surface_response']:.6f}  "
                    f"raw_response={raw_resp:.6f}  "
                    f"params={{{', '.join(f'{k}={v:.4f}' for k, v in param_values.items())}}}"
                )
                _append_result_row(
                    result_log,
                    evaluation_index=evaluation_index,
                    parameter_values=param_values,
                    objective_values=obj_vals,
                    status="success",
                    raw_response=raw_resp,
                )
        else:
            failure_reason = str(eval_result.get("error", "unknown"))
            alert(
                f"eval={evaluation_index} FAILED: {failure_reason}  "
                f"params={{{', '.join(f'{k}={v:.4f}' for k, v in param_values.items())}}}"
            )
            if suggestion_id:
                try:
                    client.update_suggestion_status(suggestion_id, "rejected")
                except Exception:
                    pass
            _append_result_row(
                result_log,
                evaluation_index=evaluation_index,
                parameter_values=param_values,
                objective_values=None,
                status="failed",
                failure_reason=failure_reason,
            )

        # --- poll delay --------------------------------------------
        time.sleep(poll_s)

    # ── post-loop: diagnostics & pause ─────────────────────────────
    event("Loop finished — fetching diagnostics")
    try:
        diag = client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=300)
        diag_path = os.path.join(artifact_dir, "diagnostics.json")
        with open(diag_path, "w") as fh:
            json.dump(diag, fh, indent=2, default=str)
        event(f"Diagnostics saved to {diag_path}")
    except Exception as exc:
        alert(f"Diagnostics fetch failed: {exc}")

    # Pause (don't terminate) so the campaign can be resumed later.
    try:
        status_check = client.next_action(campaign_id)
        if status_check.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            event("Campaign paused")
    except Exception as exc:
        alert(f"Pause failed (campaign may already be stopped): {exc}")

    # ── final summary ──────────────────────────────────────────────
    _print_summary(result_log, campaign_id, artifact_dir)

    return campaign_id


def _print_summary(result_log: str, campaign_id: str, artifact_dir: str) -> None:
    """Print a human-readable summary and write a summary JSON."""
    rows: list[dict[str, object]] = []
    if os.path.exists(result_log):
        with open(result_log) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    n_attempted = len(rows)
    n_success = sum(1 for r in rows if r.get("status") == "success")
    n_failed = n_attempted - n_success

    best_row: dict[str, object] | None = None
    best_sr = -float("inf")
    for r in rows:
        if r.get("status") == "success" and r.get("objective_values"):
            sr = float(r["objective_values"]["surface_response"])
            if sr > best_sr:
                best_sr = sr
                best_row = r

    event("=== FINAL SUMMARY ===")
    event(f"campaign_id={campaign_id}")
    event(f"attempted={n_attempted}  success={n_success}  failed={n_failed}")
    if best_row:
        event(f"best_surface_response={best_sr:.10f}")
        event(f"best_raw_response={best_row.get('raw_response', 'N/A')}")
        event(f"best_params={best_row['parameter_values']}")
    event(f"result_log={result_log}")
    event(f"BO_MCP_CAMPAIGN_ID={campaign_id}")

    summary_path = os.path.join(artifact_dir, "summary.json")
    summary: dict[str, object] = {
        "campaign_id": campaign_id,
        "n_attempted": n_attempted,
        "n_success": n_success,
        "n_failed": n_failed,
        "best_surface_response": best_sr if best_row else None,
        "best_raw_response": best_row.get("raw_response") if best_row else None,
        "best_parameter_values": best_row["parameter_values"] if best_row else None,
        "result_log": result_log,
    }
    with open(summary_path, "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    event(f"Summary saved to {summary_path}")