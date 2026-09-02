from __future__ import annotations

import argparse
import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from .autonomous_continuation import (
    DEFAULT_BO_CAMPAIGN_ID,
    DEFAULT_RECREATED_DIR,
    DEFAULT_ROBOFLEX_CAMPAIGN_ID,
    StopRequested,
    _best_effort_export_and_pause,
    _execute_one,
    _iso_now,
    _ensure_no_visible_duplicate,
    _ensure_robot_ready,
    _require_result_count_below_target,
    _sample_name,
    _stop_if_zero_no_peak_streak_exceeded,
    _update_zero_no_peak_streak,
    _validate_monitoring_args,
    _write_json,
    _append_json,
)
from .current_resume import _next_single_suggestion
from .continuation import DEFAULT_HISTORY
from .robridge_client import RobridgeClient
from .space import normalize_candidate, robridge_parameters

DEFAULT_FAILED_MEASUREMENT_DIR = DEFAULT_RECREATED_DIR / "autonomous_continuation_20260725T053043Z" / "measurement17"
DEFAULT_FAILED_SUGGESTION_ID = "a9f8598d-edd7-48fa-bbf6-b94ca3618912"


def run(args: argparse.Namespace) -> None:
    _validate_monitoring_args(args)
    failed = _load_failed_measurement(args.failed_measurement_dir, args.campaign_id, args.failed_suggestion_id)
    previous_retry = _load_previous_retry_check(args)
    plan = _plan(args, failed, previous_retry)
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

    run_dir = args.recreated_artifact_dir / f"failed_measurement_retry_continuation_{_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "plan.json", plan)
    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    new_completed = 0
    zero_no_peak_streak = int(args.initial_zero_no_peak_streak)

    try:
        _ensure_bo_running_or_resume(bo, args, run_dir)
        count = len(bo.get_results(args.campaign_id))
        if count != args.expected_current_results:
            raise StopRequested(f"Expected {args.expected_current_results} BO results before failed-measurement retry; found {count}.")
        _require_exact_single_pending(bo, args.campaign_id, args.failed_suggestion_id)

        retry_request = _request_with_retry_sample(failed["request"], args.retry_suffix, args.failed_run_id, args.failed_suggestion_id)
        measurement_dir = run_dir / f"measurement{count + 1:02d}_retry_{args.retry_suffix}"
        analysis = _execute_one(
            bo,
            rb,
            args,
            measurement_dir,
            suggestion=failed["suggestion"],
            candidate=failed["candidate"],
            request=retry_request,
            measurement_number=count + 1,
            exact_reviewed=False,
        )
        _assert_count(bo, args.campaign_id, count + 1)
        new_completed += 1
        zero_no_peak_streak = _update_zero_no_peak_streak(zero_no_peak_streak, analysis)
        _append_json(run_dir / "summary.jsonl", {"event": "completed_failed_measurement_retry", "measurement_number": count + 1, "new_completed": new_completed, "zero_no_peak_streak": zero_no_peak_streak, "analysis": analysis, "time": _iso_now()})
        _stop_if_zero_no_peak_streak_exceeded(zero_no_peak_streak, args)

        while new_completed < args.max_new_measurements:
            result_count = _require_result_count_below_target(bo, args)
            expected_now = args.expected_current_results + new_completed
            if result_count != expected_now:
                raise StopRequested(f"Expected {expected_now} BO results before next submission; found {result_count}.")
            suggestion = _next_single_suggestion(bo, args, run_dir, result_count)

            candidate = normalize_candidate(suggestion["parameter_values"])
            label = _sample_name(suggestion["suggestion_id"])
            request = {"parameters": robridge_parameters(candidate, sample_name=label), "note": f"BO-MCP RoboChemFlex yield optimization {label}"}
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
            _assert_count(bo, args.campaign_id, result_count + 1)
            new_completed += 1
            zero_no_peak_streak = _update_zero_no_peak_streak(zero_no_peak_streak, analysis)
            _append_json(run_dir / "summary.jsonl", {"event": "completed_measurement", "measurement_number": result_count + 1, "new_completed": new_completed, "zero_no_peak_streak": zero_no_peak_streak, "analysis": analysis, "time": _iso_now()})
            _stop_if_zero_no_peak_streak_exceeded(zero_no_peak_streak, args)
    except StopRequested as exc:
        _append_json(run_dir / "summary.jsonl", {"event": "stopped", "reason": str(exc), "new_completed": new_completed, "time": _iso_now()})
        print(f"Stopped safely: {exc}")
        raise SystemExit(str(exc))
    finally:
        _best_effort_export_and_pause(bo if "bo" in locals() else None, args.campaign_id, run_dir, args)
        _write_json(run_dir / "summary.json", {"campaign_id": args.campaign_id, "new_completed_this_invocation": new_completed, "target_total_results": args.target_total_results, "zero_no_peak_streak_at_exit": zero_no_peak_streak, "finished_at": _iso_now()})
        print(f"New completed experiments this invocation: {new_completed}")
        print(f"Artifacts: {run_dir}")


def _load_failed_measurement(path: Path, campaign_id: str, expected_sid: str) -> dict:
    suggestion = json.loads((path / "suggestion.json").read_text())
    candidate = normalize_candidate(json.loads((path / "candidate.json").read_text()))
    request = json.loads((path / "roboflex_request.json").read_text())
    if suggestion.get("campaign_id") != campaign_id:
        raise SystemExit(f"Failed-measurement campaign_id {suggestion.get('campaign_id')!r} does not match {campaign_id!r}.")
    if suggestion.get("suggestion_id") != expected_sid:
        raise SystemExit(f"Failed-measurement suggestion id {suggestion.get('suggestion_id')!r} does not match {expected_sid!r}.")
    return {"suggestion": suggestion, "candidate": candidate, "request": request}


def _load_previous_retry_check(args: argparse.Namespace) -> dict | None:
    path = getattr(args, "previous_retry_dir", None)
    if not path:
        return None
    path = Path(path)
    result_path = path / "roboflex_result.json"
    request_path = path / "roboflex_request.json"
    if not result_path.exists() or not request_path.exists():
        raise SystemExit(f"Previous retry artifacts are incomplete: {path}")
    result = json.loads(result_path.read_text())
    request = json.loads(request_path.read_text())
    sample = _sample_from_request(request)
    if not sample.endswith("_r2"):
        raise SystemExit(f"Previous retry sample {sample!r} does not look like the required r2 attempt.")
    expected_run_id = getattr(args, "failed_run_id", None)
    if expected_run_id and result.get("run_id") != expected_run_id:
        raise SystemExit(f"Previous retry run_id {result.get('run_id')!r} does not match expected failed run {expected_run_id!r}.")
    payload = result.get("result") if isinstance(result, dict) else {}
    if result.get("success") is not False or (isinstance(payload, dict) and payload.get("pass") is not False):
        raise SystemExit("Previous retry artifact is not a failed pass=false analysis; refusing one-more retry.")
    y = _result_yield(payload)
    if y is None or not math.isfinite(y):
        raise SystemExit("Previous retry artifact does not contain a finite yield; refusing one-more retry.")
    return {"path": str(path), "run_id": result.get("run_id"), "sample_name": sample, "yield_percent": y, "pass": payload.get("pass") if isinstance(payload, dict) else None}


def _result_yield(payload: object) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("yield", "yield_percent"):
        val = payload.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    analytes = payload.get("analytes")
    if isinstance(analytes, dict):
        for analyte in analytes.values():
            if isinstance(analyte, dict):
                val = analyte.get("yield") or analyte.get("yield_percent")
                if isinstance(val, (int, float)):
                    return float(val)
    return None


def _request_with_retry_sample(request: dict, retry_suffix: str, failed_run_id: str, suggestion_id: str) -> dict:
    updated = copy.deepcopy(request)
    old_label = None
    for param in updated["parameters"]:
        if param.get("name") == "sample_name":
            old_label = str(param.get("value"))
            param["value"] = f"{old_label}_{retry_suffix}"
            break
    if old_label is None:
        raise SystemExit("Failed-measurement request has no sample_name parameter.")
    updated["note"] = f"{request.get('note', '').strip()} retry {retry_suffix} after failed {failed_run_id}; original suggestion {suggestion_id}"
    return updated


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


def _require_exact_single_pending(bo: BoMcpClient, campaign_id: str, expected_sid: str) -> None:
    pending = bo.query_suggestions(campaign_id, status_filter="pending", limit=5)
    if len(pending) != 1:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise StopRequested(f"Expected exactly one pending suggestion before retry; found {len(pending)} ({ids}).")
    if pending[0].get("suggestion_id") != expected_sid:
        raise StopRequested(f"Pending suggestion is {pending[0].get('suggestion_id')!r}, not failed measurement suggestion {expected_sid!r}.")


def _assert_count(bo: BoMcpClient, campaign_id: str, expected: int) -> None:
    count = len(bo.get_results(campaign_id))
    if count != expected:
        raise StopRequested(f"BO result count did not increment as expected: expected={expected}, observed={count}.")


def _live_preflight(args: argparse.Namespace) -> None:
    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    failed = _load_failed_measurement(args.failed_measurement_dir, args.campaign_id, args.failed_suggestion_id)
    retry_request = _request_with_retry_sample(failed["request"], args.retry_suffix, args.failed_run_id, args.failed_suggestion_id)
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
    _require_exact_single_pending(bo, args.campaign_id, args.failed_suggestion_id)
    _ensure_robot_ready(status, args)
    _ensure_no_visible_duplicate(rb, _sample_from_request(retry_request))


def _plan(args: argparse.Namespace, failed: dict, previous_retry: dict | None = None) -> dict:
    retry_request = _request_with_retry_sample(failed["request"], args.retry_suffix, args.failed_run_id, args.failed_suggestion_id)
    return {
        "mode": "dry-run" if args.dry_run else "hardware",
        "bo_campaign_id": args.campaign_id,
        "resume_bo_if_paused": args.resume_bo_if_paused,
        "expected_current_results": args.expected_current_results,
        "target_total_results": args.target_total_results,
        "max_new_measurements": args.max_new_measurements,
        "failed_measurement_dir": str(args.failed_measurement_dir),
        "previous_retry_check": previous_retry,
        "failed_run_id": args.failed_run_id,
        "failed_suggestion_id": args.failed_suggestion_id,
        "retry_sample_name": _sample_from_request(retry_request),
        "retry_request_file_is_source_of_truth_except_sample_name_and_note": True,
        "bo_generation": {
            "general_timeout_s": args.bo_timeout_s,
            "suggestion_timeout_s": getattr(args, "bo_generate_timeout_s", None),
            "retries_after_first_attempt": getattr(args, "bo_generate_retries", None),
            "post_timeout_wait_s": getattr(args, "bo_generate_recovery_wait_s", None),
            "post_timeout_polls": getattr(args, "bo_generate_recovery_polls", None),
            "idempotency_key_reused_across_retries": True,
        },
        "blocked_suggestion_ids": [s.strip() for s in str(getattr(args, "blocked_suggestion_ids", "") or "").split(",") if s.strip()],
        "monitoring": {"poll_s": args.poll_s, "heartbeat_s": args.heartbeat_s, "quiet_stdout": args.quiet_stdout, "zero_no_peak_streak_limit": args.zero_no_peak_streak_limit},
        "safe_retry_policy": "This command performs only the explicitly user-authorized r3 attempt for the same pending suggestion after R0063/R0064 pass=false finite-yield analyses; it does not create unlimited retries and submits no BO result unless RoboFlex reports pass=true.",
        "then": "if retry passes, submit it for the original pending suggestion, then continue one BO suggestion at a time until target_total_results or max_new_measurements completed new measurements",
    }


def _sample_from_request(request: dict) -> str:
    for param in request.get("parameters", []):
        if param.get("name") == "sample_name":
            return str(param.get("value"))
    raise SystemExit("request has no sample_name")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
