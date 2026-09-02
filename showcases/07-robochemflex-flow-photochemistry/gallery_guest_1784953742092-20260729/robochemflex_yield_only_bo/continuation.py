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

from robochemflex_yield_bo.autonomous_continuation import (
    DEFAULT_ROBOFLEX_CAMPAIGN_ID,
    StopRequested,
    _ensure_no_visible_duplicate,
    _ensure_robot_ready,
    _fetch_result,
    _poll_run,
    _request_sample_name,
    _result_pass_true,
    _sample_name,
)
from robochemflex_yield_bo.continuation import DEFAULT_HISTORY, _ensure_report_passes, _equivalence_report
from robochemflex_yield_bo.evaluation import _actual_parameters
from robochemflex_yield_bo.objectives import extract_yield_percent, green_score
from robochemflex_yield_bo.robridge_client import RobridgeClient
from robochemflex_yield_bo.space import normalize_candidate, robridge_parameters

from .objectives import objective_values

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts/yield_only_robochemflex_bo"
DEFAULT_SOURCE_CAMPAIGN_ID = "ccbfc92e-c646-4943-a44d-9277f2f2d8d4"
RETRYABLE_NULL_RESULT_ERRORS = (
    "zero-size array to reduction operation minimum which has no identity",
)


def run(args: argparse.Namespace) -> None:
    plan = _plan(args)
    if args.dry_run:
        print("Yield-only continuation dry-run; no BO/RoboFlex writes performed.")
        print(json.dumps(plan, indent=2, sort_keys=True))
        if args.live_read_checks:
            _live_preflight(args)
        return

    if not args.confirm_autonomous_hardware:
        raise SystemExit("Refusing RoboFlex hardware submission without --confirm-autonomous-hardware")
    if not os.environ.get("ROBRIDGE_POST_ADAPTER"):
        raise SystemExit("ROBRIDGE_POST_ADAPTER is required for RoboFlex mutation in this environment.")

    if not args.campaign_id:
        raise SystemExit("--campaign-id for the new yield-only BO-MCP campaign is required.")

    run_dir = Path(args.artifact_dir or DEFAULT_ARTIFACT_ROOT / f"continuation_{_stamp()}")
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "plan.json", plan)
    (run_dir / "COMMAND_NOTES.txt").write_text(" ".join(os.sys.argv) + "\n")

    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    successes = 0
    try:
        _ensure_bo_ready(bo, args, run_dir)
        target_total = int(getattr(args, "target_total_results", 0) or 0)
        while successes < args.max_new_measurements:
            result_count = len(bo.get_results(args.campaign_id))
            if target_total and result_count >= target_total:
                print(f"Target total reached: {result_count}/{target_total} valid BO results.")
                break
            if result_count < args.expected_seed_count:
                raise StopRequested(f"Expected at least {args.expected_seed_count} seeded BO results; found {result_count}.")
            suggestion = _next_suggestion(bo, args, run_dir, result_count)
            candidate = normalize_candidate(suggestion["parameter_values"])
            analysis = _evaluate_with_retries(bo, rb, args, run_dir, suggestion, candidate, result_count + 1)
            successes += 1
            _append_json(run_dir / "summary.jsonl", {"event": "submitted_yield_only_result", "analysis": analysis, "time": _iso_now()})
        print(f"Invocation finished: {successes} new valid measurement(s) submitted.")
    except StopRequested as exc:
        _append_json(run_dir / "summary.jsonl", {"event": "stopped", "reason": str(exc), "time": _iso_now()})
        print(f"Stopped safely: {exc}")
        raise SystemExit(str(exc))
    finally:
        _best_effort_export_pause(bo if "bo" in locals() else None, args.campaign_id, run_dir, args)
        print(f"Artifacts: {run_dir}")


def _evaluate_with_retries(bo: BoMcpClient, rb: RobridgeClient, args: argparse.Namespace, run_dir: Path, suggestion: dict, candidate: dict, measurement_number: int) -> dict:
    sid = suggestion["suggestion_id"]
    base_label = _retry_base_label(args, sid) or _sample_name(sid)
    first_attempt, final_attempt = _attempt_window(rb, args, sid, base_label)
    last_retry_reason = None
    if first_attempt > final_attempt:
        raise StopRequested(f"Retry budget already exhausted for suggestion {sid}; no BO result submitted.")
    for attempt in range(first_attempt, final_attempt + 1):
        label = _attempt_sample_name(base_label, attempt)
        request = {"parameters": robridge_parameters(candidate, sample_name=label), "note": f"BO-MCP RoboChemFlex yield-only optimization {label}"}
        measurement_dir = run_dir / f"measurement{measurement_number:02d}_attempt{attempt}"
        measurement_dir.mkdir(parents=True, exist_ok=False)
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

        print(f"Submitting yield-only measurement #{measurement_number} attempt {attempt}/{final_attempt}: {label}")
        logfire.info("Submitting yield-only RoboFlex measurement", measurement_number=measurement_number, attempt=attempt, sample_name=label, suggestion_id=sid)
        submission = rb.submit_run(request["parameters"], request.get("note", ""))
        _write_json(measurement_dir / "roboflex_submission_response.json", {"submitted_at": _iso_now(), "response": submission})
        run_id = submission.get("run", {}).get("run_id")
        if not run_id:
            raise StopRequested("RoboFlex submission response did not include run.run_id.")
        record = _poll_run(rb, run_id, measurement_dir, args.run_timeout_s, args.poll_s, args.heartbeat_s, args.quiet_stdout)
        result = _fetch_result(rb, run_id)
        _write_json(measurement_dir / "roboflex_result.json", result)
        post_status = rb.status()
        _write_json(measurement_dir / "roboflex_status_after_result.json", post_status)

        classification = _classify_result(record, result, post_status, args)
        _write_json(measurement_dir / "result_classification.json", classification)
        if classification["action"] == "submit":
            return _submit_yield_result(bo, args, measurement_dir, suggestion, candidate, result, measurement_number, label, run_id, attempt)
        if classification["action"] == "retry" and attempt < final_attempt:
            last_retry_reason = classification["reason"]
            _append_json(run_dir / "summary.jsonl", {"event": "retrying_nmr_qc_failure", "run_id": run_id, "attempt": attempt, "reason": last_retry_reason, "time": _iso_now()})
            print(f"Retrying NMR/QC failure (attempt {attempt} of {final_attempt} failed): {last_retry_reason}")
            time.sleep(float(args.retry_pause_s))
            continue
        if classification["action"] == "retry":
            raise StopRequested(f"NMR/QC retry budget exhausted for suggestion {sid}; last run {run_id}. No BO result submitted.")
        raise StopRequested(f"RoboFlex run {run_id} is not safely retryable/submittable: {classification['reason']}. No BO result submitted.")
    raise StopRequested(f"Retry loop ended unexpectedly for suggestion {sid}; last reason={last_retry_reason}")


def _retry_base_label(args: argparse.Namespace, suggestion_id: str) -> str | None:
    if getattr(args, "required_pending_suggestion_id", None) == suggestion_id:
        return getattr(args, "retry_base_sample_name", None)
    return None


def _attempt_window(rb: RobridgeClient, args: argparse.Namespace, suggestion_id: str, base_label: str) -> tuple[int, int]:
    final_attempt = int(getattr(args, "max_nmr_retries", 0)) + 1
    prior = int(getattr(args, "retry_prior_attempts", 0) or 0) if getattr(args, "required_pending_suggestion_id", None) == suggestion_id else 0
    used = _visible_attempt_numbers(rb, base_label)
    first_attempt = max(prior, max(used, default=0)) + 1
    return first_attempt, final_attempt


def _visible_attempt_numbers(rb: RobridgeClient, base_label: str) -> list[int]:
    attempts: list[int] = []
    for run in rb.list_runs().get("runs", []):
        names = [p.get("value") for p in run.get("parameters", []) if isinstance(p, dict) and p.get("name") == "sample_name"]
        note = str(run.get("note") or "")
        for attempt in range(1, 12):
            label = _attempt_sample_name(base_label, attempt)
            if label in names or label in note:
                attempts.append(attempt)
    return attempts


def _attempt_sample_name(base_label: str, attempt: int) -> str:
    return base_label if attempt == 1 else f"{base_label}_r{attempt}"


def _submit_yield_result(bo: BoMcpClient, args: argparse.Namespace, measurement_dir: Path, suggestion: dict, candidate: dict, result: dict, measurement_number: int, label: str, run_id: str, attempt: int) -> dict:
    y = extract_yield_percent(result.get("result"))
    actual = _actual_parameters(candidate, result.get("parameters") or [])
    objectives = objective_values(y)
    if set(objectives) != {"yield_percent"} or not math.isfinite(float(objectives["yield_percent"])):
        raise StopRequested("Non-finite yield-only objective; no BO result submitted.")
    analysis = _analysis(result.get("result"), objectives["yield_percent"])
    analysis.update({"measurement_number": measurement_number, "sample_name": label, "run_id": run_id, "suggestion_id": suggestion["suggestion_id"], "attempt": attempt})
    _write_json(measurement_dir / "analysis.json", analysis)
    bo_payload = {
        "parameter_values": actual,
        "objective_values": objectives,
        "suggestion_id": suggestion["suggestion_id"],
        "metadata": {
            "external_ref": {"system": "roboflex", "id": run_id},
            "notes": f"yield-only continuation measurement {measurement_number}; sample {label}; green score audit only",
            "conditions": {"sample_name": label, "attempt": attempt, "green_score_audit": green_score(actual)},
        },
    }
    _write_json(measurement_dir / "bo_result_payload.json", bo_payload)
    key = BoMcpClient.make_idempotency_key("yield-only-result", args.campaign_id, suggestion["suggestion_id"], run_id)
    response = bo.submit_results(args.campaign_id, results=[bo_payload], idempotency_key=key, force=True)
    _write_json(measurement_dir / "bo_result_response.json", response)
    print(f"Submitted yield-only BO result for {label}: yield={objectives['yield_percent']:.2f}")
    return analysis


def _classify_result(record: dict, result: dict, status: dict, args: argparse.Namespace) -> dict:
    payload = result.get("result") if isinstance(result, dict) else None
    if record.get("status") == "failed" or record.get("success") is False:
        ok, why = _retryable_null_result_failure(record, result, status, args)
        if ok:
            return {"action": "retry", "reason": why}
        return {"action": "stop", "reason": record.get("error") or "RoboFlex run failed before analysis"}
    if _result_pass_true(payload):
        return {"action": "submit", "reason": "analysis pass=true"}
    evidence = _finite_yield_or_peak_evidence(payload)
    if evidence:
        return {"action": "retry", "reason": f"analysis/QC pass=false with finite evidence: {evidence}"}
    if result.get("status") == "failed" or result.get("success") is False:
        ok, why = _retryable_null_result_failure(record, result, status, args)
        if ok:
            return {"action": "retry", "reason": why}
        return {"action": "stop", "reason": result.get("error") or _failure_message(payload) or "RoboFlex analysis failed without finite evidence"}
    return {"action": "stop", "reason": "analysis did not report pass=true and no finite yield/peak evidence was found"}


def _retryable_null_result_failure(record: dict, result: dict, status: dict, args: argparse.Namespace) -> tuple[bool, str]:
    if result.get("result") is not None:
        return False, "result payload is not null"
    error = str(record.get("error") or result.get("error") or "")
    if not any(token in error for token in RETRYABLE_NULL_RESULT_ERRORS):
        return False, "failure error is not in retryable null-result policy"
    ok, reason = _healthy_idle_platform(status, args)
    if not ok:
        return False, reason
    return True, f"retryable stochastic NMR/analysis null-result failure while platform healthy: {error}"


def _healthy_idle_platform(status: dict, args: argparse.Namespace) -> tuple[bool, str]:
    progress = status.get("progress") or {}
    campaign = status.get("campaign") or {}
    active = progress.get("active_run_ids") or []
    campaign_ids = {campaign.get("campaign_id"), campaign.get("campaign_name")}
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
        return False, "RoboFlex is not healthy/idle for stochastic retry: " + "; ".join(failures)
    return True, "RoboFlex platform is healthy/idle"


def _finite_yield_or_peak_evidence(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("yield", "yield_percent", "concentration", "concentration_mM", "peak_integral", "integral"):
        found = _find_number(payload, key)
        if found is not None and math.isfinite(found) and abs(found) > 0:
            return f"{key}={found}"
    return None


def _find_number(obj: object, wanted: str) -> float | None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if str(key).lower().replace(" ", "_") == wanted and isinstance(val, int | float):
                return float(val)
            nested = _find_number(val, wanted)
            if nested is not None:
                return nested
    elif isinstance(obj, list):
        for val in obj:
            nested = _find_number(val, wanted)
            if nested is not None:
                return nested
    return None


def _failure_message(payload: object) -> str | None:
    if isinstance(payload, dict):
        return payload.get("failure_message") or payload.get("error")
    return None


def _analysis(payload: object, yield_percent: float) -> dict:
    return {"yield_percent": float(yield_percent), "result_pass": _result_pass_true(payload), "green_score_is_objective": False}


def _next_suggestion(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path, result_count: int) -> dict:
    pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
    expected_sid = getattr(args, "required_pending_suggestion_id", None) if result_count == int(args.expected_seed_count) + 1 else None
    if len(pending) > 1:
        ids = ", ".join(s.get("suggestion_id", "<missing>") for s in pending)
        raise StopRequested(f"Multiple pending BO suggestions found ({ids}); refusing to choose.")
    if pending:
        if expected_sid and pending[0].get("suggestion_id") != expected_sid:
            raise StopRequested(f"Pending suggestion is {pending[0].get('suggestion_id')!r}, not required {expected_sid!r}.")
        return pending[0]
    if expected_sid:
        raise StopRequested(f"Required pending suggestion {expected_sid!r} is absent; no replacement generated.")
    decision = bo.next_action(args.campaign_id)
    _write_json(run_dir / f"bo_next_action_after_{result_count:02d}.json", decision)
    if decision.get("action") != "bo_generate_suggestions":
        raise StopRequested(f"BO next_action={decision.get('action')!r}; no hardware submission made.")
    response = bo._json_request("POST", f"/api/v1/suggestions/{args.campaign_id}/generate", params={"batch_size": 1}, headers={"Idempotency-Key": BoMcpClient.make_idempotency_key("yield-only-suggestion", args.campaign_id, str(result_count), run_dir.name)}, timeout=float(args.bo_generate_timeout_s))
    _write_json(run_dir / f"bo_generate_after_{result_count:02d}.json", response)
    suggestions = response.get("suggestions") or []
    if len(suggestions) != 1:
        raise StopRequested(f"Expected exactly one BO suggestion; received {len(suggestions)}.")
    return suggestions[0]


def _ensure_bo_ready(bo: BoMcpClient, args: argparse.Namespace, run_dir: Path) -> None:
    status = bo.get_campaign(args.campaign_id).get("status")
    _write_json(run_dir / "bo_status_before_continue.json", {"status": status, "checked_at": _iso_now()})
    if status == "paused" and args.resume_bo_if_paused:
        _write_json(run_dir / "bo_resume_response.json", bo.lifecycle(args.campaign_id, action="resume"))
        status = bo.get_campaign(args.campaign_id).get("status")
    if status not in {"running", "created"}:
        raise StopRequested(f"BO campaign status is {status!r}, not runnable.")


def _live_preflight(args: argparse.Namespace) -> None:
    bo = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    rb = RobridgeClient()
    if args.campaign_id:
        campaign = bo.get_campaign(args.campaign_id)
        results = bo.get_results(args.campaign_id)
        pending = bo.query_suggestions(args.campaign_id, status_filter="pending", limit=5)
        print(f"Yield-only BO status: {campaign.get('status')}; results={len(results)}; pending={[s.get('suggestion_id') for s in pending]}")
        if len(results) < args.expected_seed_count:
            raise SystemExit(f"Expected at least {args.expected_seed_count} seeded BO results; found {len(results)}.")
        expected_sid = getattr(args, "required_pending_suggestion_id", None)
        if expected_sid and [s.get("suggestion_id") for s in pending] != [expected_sid]:
            raise SystemExit(f"Expected exactly pending suggestion {expected_sid}; found {[s.get('suggestion_id') for s in pending]}.")
        target_total = int(getattr(args, "target_total_results", 0) or 0)
        if target_total:
            print(f"Yield-only target total: {target_total}; remaining valid results: {max(0, target_total - len(results))}")
    source = bo.get_campaign(args.source_campaign_id)
    print(f"Source mixed-objective BO status: {source.get('status')}; results={len(bo.get_results(args.source_campaign_id))}")
    status = rb.status()
    current = rb.current_campaign()
    print(f"RoboFlex: mode={status.get('mode')} phase={status.get('phase')} state={status.get('progress', {}).get('state')} campaign={current.get('campaign_id')}")
    _ensure_robot_ready(status, args)


def _plan(args: argparse.Namespace) -> dict:
    return {
        "mode": "dry-run" if args.dry_run else "hardware",
        "yield_only_campaign_id": args.campaign_id,
        "source_mixed_objective_campaign_id": args.source_campaign_id,
        "expected_seed_count": args.expected_seed_count,
        "expected_roboflex_campaign_id": args.expected_roboflex_campaign_id,
        "max_new_measurements_this_invocation": args.max_new_measurements,
        "target_total_results": getattr(args, "target_total_results", None),
        "required_pending_suggestion_id": getattr(args, "required_pending_suggestion_id", None),
        "retry_base_sample_name": getattr(args, "retry_base_sample_name", None),
        "nmr_retry_policy": "initial attempt plus up to max_nmr_retries retry submissions; pass=true with valid yield is submitted; analysis/QC pass=false with finite yield/peak evidence is retryable; null-result failure 'zero-size array to reduction operation minimum which has no identity' is retryable only when RoboFlex remains mode=hardware, phase=running, progress.state=awaiting_run with no queued/active runs; stop without BO result on retry exhaustion or unsafe platform state",
        "will_submit_hardware": not args.dry_run,
        "operator_confirmation_required": True,
    }


def _best_effort_export_pause(bo: BoMcpClient | None, campaign_id: str | None, run_dir: Path, args: argparse.Namespace) -> None:
    if bo is None or not campaign_id:
        return
    try:
        content, content_type = bo.export_campaign(campaign_id, fmt="csv")
        (run_dir / "bo_campaign_export.csv").write_bytes(content)
        (run_dir / "bo_campaign_export.content_type.txt").write_text(content_type + "\n")
    except Exception as exc:
        print(f"BO export skipped: {exc}")
    if args.pause_bo_on_exit:
        try:
            if bo.get_campaign(campaign_id).get("status") == "running":
                bo.lifecycle(campaign_id, action="pause")
                print("BO campaign paused.")
        except Exception as exc:
            print(f"BO pause skipped: {exc}")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
