from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError
from requests.exceptions import Timeout as RequestsTimeout

from .autonomous_continuation import (
    DEFAULT_BO_CAMPAIGN_ID,
    DEFAULT_RECREATED_DIR,
    DEFAULT_ROBOFLEX_CAMPAIGN_ID,
    StopRequested,
    _append_json,
    _best_effort_export_and_pause,
    _ensure_no_visible_duplicate,
    _ensure_robot_ready,
    _execute_one,
    _iso_now,
    _sample_name,
    _stop_if_zero_no_peak_streak_exceeded,
    _update_zero_no_peak_streak,
    _validate_monitoring_args,
    _write_json,
)
from .continuation import DEFAULT_HISTORY
from .robridge_client import RobridgeClient
from .space import normalize_candidate, robridge_parameters

DEFAULT_FAILED17_SUGGESTION_ID = "a9f8598d-edd7-48fa-bbf6-b94ca3618912"


def run(args: argparse.Namespace) -> None:
    _validate_monitoring_args(args)
    plan = _plan(args)
    if args.dry_run:
        print("Dry-run plan only; no BO/RoboFlex writes performed.")
        print(json.dumps(plan, indent=2, sort_keys=True))
        if args.live_read_checks:
            _live_preflight(args)
        return

    if not args.confirm_autonomous_hardware:
        raise SystemExit("Refusing hardware execution without --confirm-autonomous-hardware")
    if not os.environ.get("ROBRIDGE_POST_ADAPTER"):
        raise SystemExit("ROBRIDGE_POST_ADAPTER is required for RoboFlex hardware submission in this environment.")

    run_dir = args.recreated_artifact_dir / f"resume_from18_to20_{_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "plan.json", plan)
    (run_dir / "COMMAND_NOTES.txt").write_text(" ".join(os.sys.argv) + "\n")

    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    new_completed = 0
    zero_no_peak_streak = int(args.initial_zero_no_peak_streak)

    try:
        _ensure_bo_running_or_resume(bo, args, run_dir)
        _require_exact_result_count(bo, args.campaign_id, args.expected_current_results, "at resume start")
        _require_no_initial_pending(bo, args)

        while new_completed < args.max_new_measurements:
            result_count = len(bo.get_results(args.campaign_id))
            if result_count >= args.target_total_results:
                raise StopRequested(f"BO campaign already has {result_count} result(s), target is {args.target_total_results}.")
            expected_now = args.expected_current_results + new_completed
            if result_count != expected_now:
                raise StopRequested(f"Expected {expected_now} BO results before next submission; found {result_count}.")

            suggestion = _next_single_suggestion(bo, args, run_dir, result_count)
            _reject_blocked_suggestion(suggestion, args)
            candidate = normalize_candidate(suggestion["parameter_values"])
            label = _sample_name(suggestion["suggestion_id"])
            request = {
                "parameters": robridge_parameters(candidate, sample_name=label),
                "note": f"BO-MCP RoboChemFlex yield optimization {label}",
            }
            measurement_dir = run_dir / f"measurement{result_count + 1:02d}"
            analysis = _execute_one(
                bo,
                rb,
                args,
                measurement_dir,
                suggestion=suggestion,
                candidate=candidate,
                request=request,
                measurement_number=result_count + 1,
                exact_reviewed=False,
            )
            _require_exact_result_count(bo, args.campaign_id, result_count + 1, "after BO result submission")
            new_completed += 1
            zero_no_peak_streak = _update_zero_no_peak_streak(zero_no_peak_streak, analysis)
            _append_json(
                run_dir / "summary.jsonl",
                {
                    "event": "completed_measurement",
                    "measurement_number": result_count + 1,
                    "new_completed": new_completed,
                    "zero_no_peak_streak": zero_no_peak_streak,
                    "analysis": analysis,
                    "time": _iso_now(),
                },
            )
            _stop_if_zero_no_peak_streak_exceeded(zero_no_peak_streak, args)

        final_count = len(bo.get_results(args.campaign_id))
        if final_count != args.target_total_results:
            raise StopRequested(f"Invocation budget ended at {final_count} BO results, expected target {args.target_total_results}.")
        _append_json(run_dir / "summary.jsonl", {"event": "target_reached", "bo_results": final_count, "time": _iso_now()})
        print(f"Target reached: {final_count} BO results.")
    except StopRequested as exc:
        _append_json(run_dir / "summary.jsonl", {"event": "stopped", "reason": str(exc), "new_completed": new_completed, "time": _iso_now()})
        print(f"Stopped safely: {exc}")
        raise SystemExit(str(exc))
    finally:
        _best_effort_export_and_pause(bo if "bo" in locals() else None, args.campaign_id, run_dir, args)
        _write_json(
            run_dir / "summary.json",
            {
                "campaign_id": args.campaign_id,
                "new_completed_this_invocation": new_completed,
                "target_total_results": args.target_total_results,
                "zero_no_peak_streak_at_exit": zero_no_peak_streak,
                "finished_at": _iso_now(),
            },
        )
        print(f"New completed experiments this invocation: {new_completed}")
        print(f"Artifacts: {run_dir}")


def _next_single_suggestion(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path, result_count: int) -> dict:
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    if pending:
        return _single_pending_or_stop(pending, "before generation")

    decision = bo.next_action(args.campaign_id)
    _write_json(run_dir / f"bo_next_action_after_{result_count:02d}.json", decision)
    if decision.get("action") != "bo_generate_suggestions":
        raise StopRequested(f"BO next_action={decision.get('action')!r}; stopping before hardware submission.")

    attempts = int(getattr(args, "bo_generate_retries", 0)) + 1
    idempotency_key = BoMcpClient.make_idempotency_key("suggestion", args.campaign_id, str(result_count), run_dir.name)
    last_error = None
    for attempt in range(1, attempts + 1):
        _append_json(
            run_dir / "summary.jsonl",
            {
                "event": "generate_suggestions_attempt",
                "attempt": attempt,
                "max_attempts": attempts,
                "after_result_count": result_count,
                "timeout_s": float(args.bo_generate_timeout_s),
                "time": _iso_now(),
            },
        )
        try:
            response = _generate_suggestions_with_timeout(bo, args, idempotency_key)
        except RequestsTimeout as exc:
            last_error = exc
            _append_json(
                run_dir / "summary.jsonl",
                {
                    "event": "generate_suggestions_timeout",
                    "attempt": attempt,
                    "after_result_count": result_count,
                    "error": str(exc),
                    "action": "poll_results_progress_pending_before_retry_or_hardware",
                    "time": _iso_now(),
                },
            )
            recovered = _poll_recovery_after_generate_timeout(bo, args, run_dir, result_count, exc, attempt)
            if recovered is not None:
                return recovered
            if attempt < attempts:
                continue
            break
        except BoMcpClientError as exc:
            last_error = exc
            if "409" in str(exc) and "IDEMPOTENCY" in str(exc).upper():
                recovered = _poll_recovery_after_generate_timeout(bo, args, run_dir, result_count, exc, attempt)
                if recovered is not None:
                    return recovered
                if attempt < attempts:
                    continue
            raise

        _write_json(run_dir / f"bo_generate_after_{result_count:02d}_attempt{attempt}.json", response)
        suggestion = _single_generated_or_stop(response, "generate_suggestions")
        _append_json(
            run_dir / "summary.jsonl",
            {"event": "generated_single_suggestion", "attempt": attempt, "suggestion_id": suggestion.get("suggestion_id"), "time": _iso_now()},
        )
        return suggestion

    final_state = _query_bo_recovery_state(bo, args, run_dir, result_count, "final")
    raise StopRequested(
        "BO suggestion generation did not produce exactly one pending/new suggestion "
        f"after {attempts} attempt(s); pending={len(final_state['pending'])}, "
        f"results={final_state['result_count']}; last_error={last_error}. No hardware submission made."
    )


def _generate_suggestions_with_timeout(bo: BoMcpClient, args: argparse.Namespace, idempotency_key: str) -> dict:
    return bo._json_request(
        "POST",
        f"/api/v1/suggestions/{args.campaign_id}/generate",
        params={"batch_size": 1},
        headers={"Idempotency-Key": idempotency_key},
        timeout=float(args.bo_generate_timeout_s),
    )


def _single_generated_or_stop(response: dict, context: str) -> dict:
    suggestions = response.get("suggestions") or []
    if len(suggestions) != 1:
        raise StopRequested(f"Expected exactly one BO suggestion from {context}; received {len(suggestions)}.")
    suggestion = suggestions[0]
    if suggestion.get("status") != "pending":
        raise StopRequested(f"Generated BO suggestion status is {suggestion.get('status')!r}, not 'pending'; no hardware submission made.")
    return suggestion


def _poll_recovery_after_generate_timeout(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path, result_count: int, exc: BaseException, attempt: int) -> dict | None:
    polls = int(getattr(args, "bo_generate_recovery_polls", 1))
    wait_s = float(getattr(args, "bo_generate_recovery_wait_s", 120.0))
    for poll in range(1, polls + 1):
        if poll > 1 or wait_s > 0:
            time.sleep(wait_s)
        state = _query_bo_recovery_state(bo, args, run_dir, result_count, f"attempt{attempt}_poll{poll}")
        if state["result_count"] != result_count:
            raise StopRequested(
                f"After generate_suggestions timeout, BO result count changed from {result_count} to {state['result_count']}; no hardware submission made."
            )
        pending = state["pending"]
        if len(pending) == 1:
            suggestion = pending[0]
            _reject_blocked_suggestion(suggestion, args)
            _append_json(
                run_dir / "summary.jsonl",
                {"event": "recovered_single_pending_after_generate_timeout", "attempt": attempt, "poll": poll, "suggestion_id": suggestion.get("suggestion_id"), "time": _iso_now()},
            )
            return suggestion
        if len(pending) > 1:
            ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
            raise StopRequested(f"After generate_suggestions timeout, found multiple pending suggestions ({ids}); no hardware submission made.")
    _append_json(
        run_dir / "summary.jsonl",
        {"event": "no_pending_after_generate_timeout_polls", "attempt": attempt, "polls": polls, "error": str(exc), "time": _iso_now()},
    )
    return None


def _query_bo_recovery_state(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path, result_count: int, label: str) -> dict:
    results = bo.get_results(args.campaign_id)
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    try:
        progress = bo.next_action(args.campaign_id)
        progress_error = None
    except (RequestsTimeout, BoMcpClientError) as exc:
        progress = None
        progress_error = str(exc)
    state = {
        "label": label,
        "expected_result_count": result_count,
        "result_count": len(results),
        "pending_suggestion_ids": [s.get("suggestion_id") for s in pending],
        "progress": progress,
        "progress_error": progress_error,
        "checked_at": _iso_now(),
    }
    _write_json(run_dir / f"bo_generate_recovery_{label}_after_{result_count:02d}.json", state)
    return {"result_count": len(results), "pending": pending, "progress": progress}


def _single_pending_or_stop(pending: list[dict], context: str) -> dict:
    if len(pending) != 1:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise StopRequested(f"Multiple pending BO suggestions found {context} ({ids}); refusing to choose.")
    return pending[0]


def _reject_blocked_suggestion(suggestion: dict, args: argparse.Namespace) -> None:
    sid = suggestion.get("suggestion_id")
    blocked = {s.strip() for s in str(args.blocked_suggestion_ids or "").split(",") if s.strip()}
    if sid in blocked:
        raise StopRequested(f"Pending suggestion {sid} is blocked from retry by this resume command; no hardware submission made.")


def _ensure_bo_running_or_resume(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path) -> None:
    status = bo.get_campaign(args.campaign_id).get("status")
    _write_json(run_dir / "bo_status_before_resume.json", {"status": status, "checked_at": _iso_now()})
    if status == "paused" and args.resume_bo_if_paused:
        response = bo.lifecycle(args.campaign_id, action="resume")
        _write_json(run_dir / "bo_resume_response.json", response)
        print("BO campaign resumed from paused state.")
        status = bo.get_campaign(args.campaign_id).get("status")
    if status != "running":
        raise StopRequested(f"BO campaign status is {status!r}, not running; cannot continue.")


def _require_no_initial_pending(bo: BoMcpClient, args: argparse.Namespace) -> None:
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    if pending:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise StopRequested(f"Expected no pending BO suggestions at resume start; found {len(pending)} ({ids}).")


def _require_exact_result_count(bo: BoMcpClient, campaign_id: str, expected: int, context: str) -> None:
    count = len(bo.get_results(campaign_id))
    if count != expected:
        raise StopRequested(f"Expected {expected} BO result(s) {context}; found {count}.")


def _live_preflight(args: argparse.Namespace) -> None:
    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    campaign = bo.get_campaign(args.campaign_id)
    results = bo.get_results(args.campaign_id)
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    status = rb.status()
    print(f"Live BO status: {campaign.get('status')}; results: {len(results)}; pending: {[s.get('suggestion_id') for s in pending]}")
    print(f"Live RoboFlex: mode={status.get('mode')} phase={status.get('phase')} progress={status.get('progress', {}).get('state')}")
    if campaign.get("status") not in {"paused", "running"}:
        raise SystemExit(f"Expected BO campaign paused/running, found {campaign.get('status')!r}.")
    if len(results) != args.expected_current_results:
        raise SystemExit(f"Expected {args.expected_current_results} BO results, found {len(results)}.")
    if pending:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise SystemExit(f"Expected no pending suggestions for from-current resume, found {len(pending)} ({ids}).")
    _ensure_robot_ready(status, args)


def _plan(args: argparse.Namespace) -> dict:
    return {
        "mode": "dry-run" if args.dry_run else "hardware",
        "bo_campaign_id": args.campaign_id,
        "expected_current_results": args.expected_current_results,
        "target_total_results": args.target_total_results,
        "max_new_measurements": args.max_new_measurements,
        "resume_bo_if_paused": args.resume_bo_if_paused,
        "bo_generation": {
            "general_timeout_s": args.bo_timeout_s,
            "suggestion_timeout_s": args.bo_generate_timeout_s,
            "retries_after_first_attempt": args.bo_generate_retries,
            "post_timeout_wait_s": args.bo_generate_recovery_wait_s,
            "post_timeout_polls": args.bo_generate_recovery_polls,
            "idempotency_key_reused_across_retries": True,
        },
        "blocked_suggestion_ids": [s.strip() for s in str(args.blocked_suggestion_ids or "").split(",") if s.strip()],
        "expected_roboflex_campaign_id": args.expected_roboflex_campaign_id,
        "monitoring": {
            "poll_s": args.poll_s,
            "heartbeat_s": args.heartbeat_s,
            "quiet_stdout": args.quiet_stdout,
            "zero_no_peak_streak_limit": args.zero_no_peak_streak_limit,
            "initial_zero_no_peak_streak": args.initial_zero_no_peak_streak,
        },
        "safety": [
            "start only from exactly expected_current_results and zero pending suggestions",
            "generate one BO suggestion at a time",
            "generate_suggestions uses a longer timeout and one idempotency key reused across retries",
            "after generate_suggestions timeout/409, wait and poll BO results, next_action progress, and pending suggestions before retry or hardware",
            "continue to hardware only with exactly one pending/generated suggestion; otherwise pause/stop safely",
            "verify RoboFlex idle/awaiting_run and expected campaign before every hardware submission",
            "write request/history equivalence report before every hardware submission",
            "never submit blocked failed17 suggestion id",
        ],
    }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
