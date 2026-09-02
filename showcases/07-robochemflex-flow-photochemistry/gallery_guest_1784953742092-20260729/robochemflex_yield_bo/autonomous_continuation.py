from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient

from .continuation import DEFAULT_HISTORY, _ensure_report_passes, _equivalence_report
from .evaluation import _actual_parameters
from .objectives import extract_yield_percent, objective_values
from .robridge_client import RobridgeClient
from .space import normalize_candidate, robridge_parameters

DEFAULT_BO_CAMPAIGN_ID = "ccbfc92e-c646-4943-a44d-9277f2f2d8d4"
DEFAULT_RECREATED_DIR = Path("artifacts/recreated_robochemflex_yield_bo_20260725")
DEFAULT_PREVIEW_DIR = DEFAULT_RECREATED_DIR / "measurement10_preview"
DEFAULT_PREVIEW_SUGGESTION_ID = "98f9b554-6ff2-4a08-8e32-2fdecd211e10"
DEFAULT_ROBOFLEX_CAMPAIGN_ID = "robochemflex_yield_bo_fresh_20260724T155503Z-20260724-175502"


class StopRequested(RuntimeError):
    pass


def _validate_monitoring_args(args: argparse.Namespace) -> None:
    if not 120.0 <= float(args.poll_s) <= 300.0:
        raise SystemExit("--poll-s must be between 120 and 300 seconds for production hardware monitoring.")
    if not 1800.0 <= float(args.heartbeat_s) <= 3600.0:
        raise SystemExit("--heartbeat-s must be between 1800 and 3600 seconds (30-60 minutes).")
    if int(args.zero_no_peak_streak_limit) < 1:
        raise SystemExit("--zero-no-peak-streak-limit must be at least 1.")


def run(args: argparse.Namespace) -> None:
    _validate_monitoring_args(args)
    preview = _load_measurement10_preview(args.preview_dir, args.campaign_id, args.measurement10_suggestion_id)
    plan = _plan(args, preview)

    if args.dry_run:
        print_plan(plan)
        if args.live_read_checks:
            _live_preflight(args, preview)
        return

    if not args.confirm_autonomous_hardware:
        raise SystemExit("Refusing hardware execution without --confirm-autonomous-hardware")
    if not os.environ.get("ROBRIDGE_POST_ADAPTER"):
        raise SystemExit("ROBRIDGE_POST_ADAPTER is required for RoboFlex hardware submission in this environment.")

    run_dir = args.recreated_artifact_dir / f"autonomous_continuation_{_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "plan.json", plan)
    _write_text(run_dir / "COMMAND_NOTES.txt", " ".join(os.sys.argv) + "\n")

    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    new_completed = 0
    zero_no_peak_streak = 0

    try:
        initial_count = len(bo.get_results(args.campaign_id))
        if initial_count != args.expected_initial_results:
            raise StopRequested(f"Expected {args.expected_initial_results} BO results before measurement #10; found {initial_count}.")

        # Measurement #10 is the reviewed artifact. Never generate a replacement for it.
        before_count = _require_result_count_below_target(bo, args)
        _require_pending_measurement10(bo, args.campaign_id, args.measurement10_suggestion_id)
        measurement_dir = run_dir / f"measurement{before_count + 1:02d}"
        analysis = _execute_one(
            bo,
            rb,
            args,
            measurement_dir,
            suggestion=preview["suggestion"],
            candidate=preview["candidate"],
            request=preview["request"],
            measurement_number=before_count + 1,
            exact_reviewed=True,
        )
        _assert_result_count_incremented(bo, args.campaign_id, before_count)
        new_completed += 1
        zero_no_peak_streak = _update_zero_no_peak_streak(zero_no_peak_streak, analysis)
        _append_json(run_dir / "summary.jsonl", {"event": "completed_measurement", "measurement_number": before_count + 1, "new_completed": new_completed, "zero_no_peak_streak": zero_no_peak_streak, "analysis": analysis, "time": _iso_now()})
        _stop_if_zero_no_peak_streak_exceeded(zero_no_peak_streak, args)

        while new_completed < args.max_new_experiments:
            result_count = _require_result_count_below_target(bo, args)
            pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
            if len(pending) > 1:
                ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
                raise StopRequested(f"Multiple pending BO suggestions found after measurement #10 ({ids}); refusing to choose.")
            if pending:
                suggestion = pending[0]
            else:
                decision = bo.next_action(args.campaign_id)
                _write_json(run_dir / f"bo_next_action_after_{result_count:02d}.json", decision)
                if decision.get("action") != "bo_generate_suggestions":
                    raise StopRequested(f"BO next_action={decision.get('action')!r}; stopping autonomous continuation.")
                response = bo.generate_suggestions(args.campaign_id, batch_size=1)
                _write_json(run_dir / f"bo_generate_after_{result_count:02d}.json", response)
                suggestions = response.get("suggestions") or []
                if len(suggestions) != 1:
                    raise StopRequested(f"Expected exactly one BO suggestion; received {len(suggestions)}.")
                suggestion = suggestions[0]

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
            _assert_result_count_incremented(bo, args.campaign_id, result_count)
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


def _execute_one(bo: BoMcpClient, rb: RobridgeClient, args: argparse.Namespace, measurement_dir: Path, *, suggestion: dict, candidate: dict, request: dict, measurement_number: int, exact_reviewed: bool) -> dict:
    measurement_dir.mkdir(parents=True, exist_ok=False)
    label = _request_sample_name(request)
    sid = suggestion["suggestion_id"]
    _write_json(measurement_dir / "suggestion.json", suggestion)
    _write_json(measurement_dir / "candidate.json", candidate)
    _write_json(measurement_dir / "roboflex_request.json", request)

    report = _equivalence_report(request, args.history_path)
    _ensure_report_passes(report)
    _write_json(measurement_dir / "equivalence_report.json", report)

    status = rb.status()
    _write_json(measurement_dir / "roboflex_status_before_submit.json", status)
    _ensure_robot_ready(status, args)
    _ensure_no_visible_duplicate(rb, label)

    print(f"Submitting measurement #{measurement_number}: {label} ({'reviewed #10' if exact_reviewed else sid})")
    logfire.info("Submitting RoboFlex measurement", measurement_number=measurement_number, sample_name=label, suggestion_id=sid)
    submission = rb.submit_run(request["parameters"], request.get("note", ""))
    _write_json(measurement_dir / "roboflex_submission_response.json", {"submitted_at": _iso_now(), "response": submission})
    run_id = submission.get("run", {}).get("run_id")
    if not run_id:
        raise StopRequested("RoboFlex submission response did not include run.run_id.")

    record = _poll_run(rb, run_id, measurement_dir, args.run_timeout_s, args.poll_s, args.heartbeat_s, args.quiet_stdout)
    result = _fetch_result(rb, run_id)
    _write_json(measurement_dir / "roboflex_result.json", result)
    failure = _failure_message(record, result)
    if failure:
        raise StopRequested(f"RoboFlex run {run_id} failed; no BO result submitted. Failure: {failure}")


    if not _result_pass_true(result.get("result")):
        raise StopRequested(f"RoboFlex run {run_id} did not report pass=true; no BO result submitted.")
    y = extract_yield_percent(result.get("result"))
    actual = _actual_parameters(candidate, result.get("parameters") or [])
    objectives = objective_values(actual, y)
    if not _finite_objectives(objectives):
        raise StopRequested(f"Non-finite objective values for {label}; no BO result submitted.")
    analysis = _result_analysis(result.get("result"), objectives)
    analysis.update({"measurement_number": measurement_number, "sample_name": label, "run_id": run_id, "suggestion_id": sid})
    _write_json(measurement_dir / "analysis.json", analysis)
    _print_completed_analysis(analysis)
    bo_payload = {
        "parameter_values": actual,
        "objective_values": objectives,
        "suggestion_id": sid,
        "metadata": {
            "external_ref": {"system": "roboflex", "id": run_id},
            "notes": f"autonomous continuation measurement {measurement_number}; sample {label}",
        },
    }
    _write_json(measurement_dir / "bo_result_payload.json", bo_payload)
    key = BoMcpClient.make_idempotency_key("result", args.campaign_id, sid, run_id)
    response = bo.submit_results(args.campaign_id, results=[bo_payload], idempotency_key=key, force=True)
    _write_json(measurement_dir / "bo_result_response.json", response)
    _append_json(args.recreated_artifact_dir / "autonomous_continuation_submitted_results.jsonl", {"measurement_number": measurement_number, "sample_name": label, "run_id": run_id, "suggestion_id": sid, "objective_values": objectives, "analysis": analysis, "time": _iso_now()})
    print(f"Submitted BO result for {label}: yield={objectives['yield_percent']:.2f}, green={objectives['green_score']:.2f}")
    return analysis


def _load_measurement10_preview(preview_dir: Path, campaign_id: str, expected_sid: str) -> dict:
    suggestion_path = preview_dir / "measurement10_suggestion.json"
    request_path = preview_dir / "measurement10_roboflex_request.json"
    report_path = preview_dir / "measurement10_equivalence_report.json"
    for path in (suggestion_path, request_path, report_path):
        if not path.exists():
            raise SystemExit(f"Required measurement #10 preview artifact is missing: {path}")
    preview = json.loads(suggestion_path.read_text())
    request = json.loads(request_path.read_text())
    report = json.loads(report_path.read_text())
    if preview.get("campaign_id") != campaign_id:
        raise SystemExit(f"Measurement #10 preview campaign_id {preview.get('campaign_id')!r} does not match {campaign_id!r}.")
    if preview.get("suggestion", {}).get("suggestion_id") != expected_sid:
        raise SystemExit("Measurement #10 preview suggestion id does not match the required reviewed pending suggestion.")
    if preview.get("sample_name") != _request_sample_name(request):
        raise SystemExit("Measurement #10 preview sample_name does not match reviewed request sample_name.")
    _ensure_report_passes(report)
    return {"suggestion": preview["suggestion"], "candidate": normalize_candidate(preview["candidate"]), "request": request, "report": report}


def _live_preflight(args: argparse.Namespace, preview: dict) -> None:
    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    count = len(bo.get_results(args.campaign_id))
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    status = rb.status()
    print(f"Live BO results: {count}; pending suggestions: {[s.get('suggestion_id') for s in pending]}")
    print(f"Live RoboFlex: mode={status.get('mode')} phase={status.get('phase')} progress={status.get('progress', {}).get('state')}")
    if count != args.expected_initial_results:
        raise SystemExit(f"Expected {args.expected_initial_results} live BO results; found {count}.")
    _require_pending_measurement10(bo, args.campaign_id, args.measurement10_suggestion_id)
    _ensure_robot_ready(status, args)
    _ensure_no_visible_duplicate(rb, preview["request"] and _request_sample_name(preview["request"]))


def _plan(args: argparse.Namespace, preview: dict) -> dict:
    return {
        "mode": "dry-run" if args.dry_run else "hardware",
        "bo_campaign_id": args.campaign_id,
        "expected_initial_results": args.expected_initial_results,
        "target_total_results": args.target_total_results,
        "max_new_experiments": args.max_new_experiments,
        "monitoring": {
            "poll_s": args.poll_s,
            "heartbeat_s": args.heartbeat_s,
            "quiet_stdout": args.quiet_stdout,
            "zero_no_peak_streak_limit": args.zero_no_peak_streak_limit,
        },
        "starts_with_measurement10_preview": {
            "preview_dir": str(args.preview_dir),
            "suggestion_id": preview["suggestion"]["suggestion_id"],
            "sample_name": _request_sample_name(preview["request"]),
            "request_file_is_source_of_truth": True,
        },
        "then": "after #10 result submission, query/reuse exactly one pending suggestion or generate one BO suggestion at a time until 20 total BO results or 11 new completions",
    }


def print_plan(plan: dict) -> None:
    print("Dry-run plan only; no BO/RoboFlex writes performed.")
    print(json.dumps(plan, indent=2, sort_keys=True))


def _require_pending_measurement10(bo: BoMcpClient, campaign_id: str, expected_sid: str) -> None:
    pending = bo.query_suggestions(campaign_id, status_filter="pending", limit=5)
    if len(pending) != 1:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise StopRequested(f"Expected exactly one pending measurement #10 suggestion; found {len(pending)} ({ids}).")
    if pending[0].get("suggestion_id") != expected_sid:
        raise StopRequested(f"Pending suggestion is {pending[0].get('suggestion_id')!r}, not reviewed #10 {expected_sid!r}.")


def _require_result_count_below_target(bo: BoMcpClient, args: argparse.Namespace) -> int:
    count = len(bo.get_results(args.campaign_id))
    if count >= args.target_total_results:
        raise StopRequested(f"BO campaign already has {count} result(s), target is {args.target_total_results}.")
    return count


def _assert_result_count_incremented(bo: BoMcpClient, campaign_id: str, before_count: int) -> None:
    after = len(bo.get_results(campaign_id))
    if after != before_count + 1:
        raise StopRequested(f"BO result count did not increment as expected: before={before_count}, after={after}.")


def _ensure_robot_ready(status: dict, args: argparse.Namespace) -> None:
    progress = status.get("progress") or {}
    campaign = status.get("campaign") or {}
    active = progress.get("active_run_ids") or []
    campaign_ids = {campaign.get("campaign_id"), campaign.get("campaign_name")}
    failures = []
    checks = [
        (status.get("mode") == "hardware", f"mode={status.get('mode')!r}"),
        (status.get("phase") == "running", f"phase={status.get('phase')!r}"),
        (progress.get("state") == "awaiting_run", f"progress.state={progress.get('state')!r}"),
        ((progress.get("queue_depth") or 0) == 0, f"queue_depth={progress.get('queue_depth')!r}"),
        (not active, f"active_run_ids={active!r}"),
        ((status.get("runs_queued") or 0) == 0, f"runs_queued={status.get('runs_queued')!r}"),
        ((status.get("runs_running") or 0) == 0, f"runs_running={status.get('runs_running')!r}"),
        (args.expected_roboflex_campaign_id in campaign_ids, f"campaign_id/name={sorted(x for x in campaign_ids if x)!r}"),
    ]
    failures = [msg for ok, msg in checks if not ok]
    if failures:
        raise StopRequested("RoboFlex is not idle in the expected hardware campaign: " + "; ".join(failures))


def _ensure_no_visible_duplicate(rb: RobridgeClient, sample_name: str) -> None:
    runs = rb.list_runs().get("runs", [])
    unfinished = [r for r in runs if r.get("status") in {"queued", "running"}]
    if unfinished:
        ids = ", ".join(f"{r.get('run_id')}:{r.get('status')}" for r in unfinished)
        raise StopRequested(f"Visible RoboFlex unfinished run(s) exist ({ids}); refusing to submit.")
    for run in runs:
        note = str(run.get("note") or "")
        names = [p.get("value") for p in run.get("parameters", []) if isinstance(p, dict) and p.get("name") == "sample_name"]
        if sample_name in note or sample_name in names:
            raise StopRequested(f"Visible RoboFlex run {run.get('run_id')} already uses sample {sample_name}.")


def _poll_run(rb: RobridgeClient, run_id: str, measurement_dir: Path, timeout_s: float, poll_s: float, heartbeat_s: float, quiet_stdout: bool) -> dict:
    deadline = time.monotonic() + timeout_s
    last_run_state = None
    last_platform_state = None
    last_heartbeat = time.monotonic()
    last_error = None
    while time.monotonic() < deadline:
        now = time.monotonic()
        try:
            rec = rb.run_record(run_id)
            last_error = None
        except Exception as exc:
            last_error = exc
            _append_json(measurement_dir / "run_poll_trail.jsonl", {"kind": "run_error", "time": _iso_now(), "error": str(exc)})
            print(f"ALERT: transient RoboFlex run poll error for {run_id}; retrying quietly")
            logfire.info("Transient RoboFlex run poll error", run_id=run_id, error=str(exc))
            time.sleep(poll_s)
            continue
        _append_json(measurement_dir / "run_poll_trail.jsonl", {"kind": "run", "time": _iso_now(), "record": rec})
        state = rec.get("status")
        if state != last_run_state:
            print(f"RoboFlex run {run_id}: state changed to {state}")
            logfire.info("RoboFlex run state changed", run_id=run_id, status=state)
            last_run_state = state
        try:
            status = rb.status()
            _append_json(measurement_dir / "run_poll_trail.jsonl", {"kind": "status", "time": _iso_now(), "status": status})
            progress = status.get("progress") or {}
            platform_state = (status.get("phase"), progress.get("state"), progress.get("blocked_on"), progress.get("overdue"))
            if platform_state != last_platform_state:
                print(f"RoboFlex platform: phase={platform_state[0]} state={platform_state[1]} blocked_on={platform_state[2]} overdue={platform_state[3]}")
                logfire.info("RoboFlex platform state changed", phase=platform_state[0], progress_state=platform_state[1], blocked_on=platform_state[2], overdue=platform_state[3])
                last_platform_state = platform_state
            elif not quiet_stdout:
                print(f"RoboFlex run {run_id}: {state} (next poll in {poll_s:.0f}s)")
        except Exception as exc:
            _append_json(measurement_dir / "run_poll_trail.jsonl", {"kind": "status_error", "time": _iso_now(), "error": str(exc)})
            print(f"ALERT: transient RoboFlex status poll error during {run_id}; retrying quietly")
            logfire.info("Transient RoboFlex status poll error", run_id=run_id, error=str(exc))
        if state in {"completed", "failed"}:
            _write_json(measurement_dir / "roboflex_final_run_record.json", rec)
            return rec
        if now - last_heartbeat >= heartbeat_s:
            print(f"Heartbeat: RoboFlex run {run_id} still {state}; polling every {poll_s:.0f}s; detailed trail on disk.")
            _append_json(measurement_dir / "run_poll_trail.jsonl", {"kind": "heartbeat", "time": _iso_now(), "run_status": state})
            last_heartbeat = now
        time.sleep(poll_s)
    if last_error:
        raise StopRequested(f"RoboFlex run {run_id} did not finish within {timeout_s} seconds; last poll error: {last_error}")
    raise StopRequested(f"RoboFlex run {run_id} did not finish within {timeout_s} seconds.")


def _fetch_result(rb: RobridgeClient, run_id: str) -> dict:
    try:
        return rb.result(run_id)
    except Exception as exc:
        return {"run_id": run_id, "status": "unknown", "success": False, "error": f"result fetch failed: {exc}"}


def _failure_message(record: dict, result: dict) -> str | None:
    payload = result.get("result") if isinstance(result, dict) else None
    if record.get("status") == "failed" or record.get("success") is False:
        return record.get("error") or _result_failure(payload) or "RoboFlex run failed"
    if result.get("status") == "failed" or result.get("success") is False:
        return result.get("error") or _result_failure(payload) or "RoboFlex analysis failed"
    return _result_failure(payload)


def _result_failure(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    pass_value = payload.get("pass")
    if pass_value is False or (isinstance(pass_value, str) and pass_value.lower() == "false"):
        return str(payload.get("failure_message") or "analysis result reported pass=false")
    return None


def _result_pass_true(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    pass_value = payload.get("pass")
    return pass_value is True or (isinstance(pass_value, str) and pass_value.lower() == "true")


def _result_analysis(payload: object, objectives: dict[str, float]) -> dict:
    analyte = _main_analyte(payload)
    peak_source = analyte if isinstance(analyte, dict) else payload if isinstance(payload, dict) else {}
    peak_position = _first_value(peak_source, ("peak_position", "peak_position_ppm", "position_ppm"))
    peak_integral = _first_number(peak_source, ("peak_integral", "integral"))
    peak_width = _first_number(peak_source, ("peak_width", "width"))
    concentration = _first_number(peak_source, ("concentration", "concentration_mM", "calculated_concentration"))
    result_pass = _first_value(payload, ("pass",))
    no_peak = _no_peak_detected(peak_source, peak_position, peak_integral, peak_width, concentration)
    zero_yield = abs(float(objectives["yield_percent"])) <= 1e-9
    return {
        "yield_percent": float(objectives["yield_percent"]),
        "green_score": float(objectives["green_score"]),
        "result_pass": result_pass,
        "peak_position": peak_position,
        "peak_integral": peak_integral,
        "peak_width": peak_width,
        "concentration": concentration,
        "nmr_peak_found": not no_peak,
        "no_peak_alert": no_peak,
        "zero_yield_alert": zero_yield,
        "zero_or_no_peak_alert": bool(no_peak or zero_yield),
        "main_analyte": analyte,
    }


def _main_analyte(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    analytes = payload.get("analytes")
    if isinstance(analytes, dict):
        for name in ("main", "product", "target"):
            if name in analytes:
                return analytes[name]
        for val in analytes.values():
            if isinstance(val, dict):
                return val
    if isinstance(analytes, list):
        for val in analytes:
            if isinstance(val, dict) and str(val.get("name", "")).lower() in {"main", "product", "target"}:
                return val
        for val in analytes:
            if isinstance(val, dict):
                return val
    return payload


def _first_value(obj: object, keys: tuple[str, ...]) -> object:
    if not isinstance(obj, dict):
        return None
    wanted = {_norm_key(k) for k in keys}
    for key, val in obj.items():
        if _norm_key(str(key)) in wanted:
            return val
    return None


def _first_number(obj: object, keys: tuple[str, ...]) -> float | None:
    val = _first_value(obj, keys)
    if isinstance(val, int | float) and math.isfinite(float(val)):
        return float(val)
    return None


def _no_peak_detected(source: object, peak_position: object, peak_integral: float | None, peak_width: float | None, concentration: float | None) -> bool:
    if not isinstance(source, dict):
        return False
    keys = {_norm_key(str(k)) for k in source}
    has_peak_fields = bool(keys & {"peakposition", "peakpositionppm", "positionppm", "peakintegral", "integral", "peakwidth"})
    if not has_peak_fields:
        return False
    position_missing = peak_position is None or peak_position == ""
    integral_zero = peak_integral is not None and abs(peak_integral) <= 1e-12
    width_zero = peak_width is not None and abs(peak_width) <= 1e-12
    concentration_zero = concentration is None or abs(concentration) <= 1e-12
    return bool(position_missing and integral_zero and width_zero and concentration_zero)


def _norm_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _print_completed_analysis(analysis: dict) -> None:
    alert = " ALERT zero/no-peak" if analysis.get("zero_or_no_peak_alert") else ""
    print(f"Completed measurement #{analysis['measurement_number']}: {analysis['sample_name']} run={analysis['run_id']}{alert}")
    print(
        "  analysis: "
        f"yield={analysis['yield_percent']:.2f}; green={analysis['green_score']:.2f}; "
        f"pass={analysis.get('result_pass')}; peak_found={analysis['nmr_peak_found']}; "
        f"peak_position={analysis.get('peak_position')}; integral={analysis.get('peak_integral')}; "
        f"width={analysis.get('peak_width')}; concentration={analysis.get('concentration')}"
    )


def _update_zero_no_peak_streak(current: int, analysis: dict) -> int:
    next_streak = current + 1 if analysis.get("zero_or_no_peak_alert") else 0
    if next_streak:
        print(f"ALERT streak: {next_streak} consecutive zero-yield/no-peak completed experiment(s).")
    return next_streak


def _stop_if_zero_no_peak_streak_exceeded(streak: int, args: argparse.Namespace) -> None:
    if streak >= args.zero_no_peak_streak_limit:
        raise StopRequested(
            f"Zero-yield/no-peak streak reached {streak} (limit {args.zero_no_peak_streak_limit}); no further RoboFlex submissions will be made."
        )

def _best_effort_export_and_pause(bo: BoMcpClient | None, campaign_id: str, run_dir: Path, args: argparse.Namespace) -> None:
    if bo is None:
        return
    try:
        content, content_type = bo.export_campaign(campaign_id, fmt="csv")
        (run_dir / "bo_campaign_export.csv").write_bytes(content)
        (run_dir / "bo_campaign_export.content_type.txt").write_text(content_type)
    except Exception as exc:
        print(f"BO export skipped: {exc}")
    if args.pause_bo_on_exit:
        try:
            if bo.get_campaign(campaign_id).get("status") == "running":
                bo.lifecycle(campaign_id, action="pause")
                print("BO campaign paused.")
        except Exception as exc:
            print(f"BO pause skipped: {exc}")


def _request_sample_name(request: dict) -> str:
    for p in request.get("parameters", []):
        if p.get("name") == "sample_name":
            return str(p.get("value"))
    raise SystemExit("RoboFlex request has no sample_name parameter.")


def _sample_name(suggestion_id: str) -> str:
    return f"bo_{suggestion_id[:10]}"


def _finite_objectives(values: dict) -> bool:
    return set(values) == {"yield_percent", "green_score"} and all(isinstance(v, int | float) and math.isfinite(float(v)) for v in values.values())


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(payload), indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _append_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(_clean(payload), sort_keys=True) + "\n")


def _clean(obj: object) -> object:
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
