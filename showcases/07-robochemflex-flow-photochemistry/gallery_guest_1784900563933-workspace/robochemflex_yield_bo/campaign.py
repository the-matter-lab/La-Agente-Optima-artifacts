from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import logfire
from domains.bo_mcp.client import BoMcpClient

from .evaluation import evaluate
from .intake import build_intake
from .robridge_client import RobridgeClient
from .seed_design import informed_seeds
from .space import normalize_candidate


def run(args: argparse.Namespace) -> None:
    if args.mode == "robridge-real" and not args.allow_real_roboflex:
        raise SystemExit("Refusing real RoboFlex execution without --allow-real-roboflex")
    if args.mode == "robridge-real" and args.allow_hardware_retry and not args.retry_suffix:
        raise SystemExit("Use --retry-suffix (for example r2) with --allow-hardware-retry so sample names remain unique")

    artifact_dir = Path(args.artifact_dir or f"artifacts/robochemflex_yield_bo_{_stamp()}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    intake = build_intake(args.campaign_name)
    _write_json(artifact_dir / "intake.json", intake)
    _write_json(artifact_dir / "seed_plan.json", informed_seeds())

    if args.validate_only:
        print("Validating BO-MCP intake only...")
        print(client.validate_intake(intake))
        return

    campaign_id = args.campaign_id or _create_campaign(client, intake, args.run_nonce)
    print(f"BO campaign: {campaign_id}")
    if args.mode == "robridge-real":
        _ensure_robridge_campaign(args, campaign_id)

    successes = 0
    failed = False
    while successes < args.max_successes:
        existing = _list_results(client, campaign_id)
        if (not args.skip_informed_seeds) and len(existing) < len(informed_seeds()):
            idx = len(existing)
            candidate = informed_seeds()[idx]
            label = _label(f"seed{idx + 1:02d}_{campaign_id[:8]}", args.retry_suffix)
            submitted = _evaluate_and_submit(client, campaign_id, candidate, artifact_dir, label, None, args)
            if not submitted:
                failed = True
                break
            successes += 1
            continue

        pending = client.query_suggestions(campaign_id, status_filter="pending", limit=1)
        if pending:
            suggestion = pending[0]
        else:
            decision = client.next_action(campaign_id)
            if decision.get("action") != "bo_generate_suggestions":
                print(f"BO next action: {decision.get('action')}; stopping this invocation.")
                break
            response = client.generate_suggestions(campaign_id, batch_size=1)
            suggestions = response.get("suggestions", [])
            if not suggestions:
                print("No BO suggestion returned; stopping this invocation.")
                break
            suggestion = suggestions[0]
        candidate = suggestion["parameter_values"]
        sid = suggestion["suggestion_id"]
        label = _label(f"bo_{sid[:10]}", args.retry_suffix)
        submitted = _evaluate_and_submit(client, campaign_id, candidate, artifact_dir, label, sid, args)
        if not submitted:
            failed = True
            break
        successes += 1

    _export(client, campaign_id, artifact_dir)
    _finish(client, campaign_id, args)
    print(f"Completed {successes} successful evaluation(s) in this invocation.")
    print(f"Artifacts: {artifact_dir}")
    if failed and args.mode == "robridge-real":
        raise SystemExit("Stopped after RoboFlex/platform analysis failure; no BO result was submitted for the failed experiment.")


def _create_campaign(client: BoMcpClient, intake: dict, run_nonce: str | None) -> str:
    nonce = run_nonce or uuid4().hex[:10]
    client.validate_intake(intake)
    key = BoMcpClient.make_idempotency_key("create", intake["name"], nonce)
    response = client.create_campaign(intake, idempotency_key=key)
    return response["campaign_id"]


def _ensure_robridge_campaign(args: argparse.Namespace, bo_campaign_id: str) -> None:
    rb = RobridgeClient()
    status = rb.status()
    unfinished = _unfinished_runs(rb)
    if unfinished:
        ids = ", ".join(f"{r.get('run_id')}:{r.get('status')}" for r in unfinished)
        raise RuntimeError(f"RoboFlex has unfinished run(s) visible ({ids}); refusing to start/submit duplicates.")
    if status.get("phase") == "ready" and not status.get("campaign"):
        rb.start_campaign(args.experiment_type, args.analytical_method, args.robridge_campaign_name)
        print("Started RoboFlex campaign from existing setup; vial setup was not modified.")
    elif status.get("campaign"):
        print("Using current RoboFlex campaign; vial setup was not modified.")
    else:
        raise RuntimeError(f"RoboFlex is not ready for run submission: phase={status.get('phase')}")


def _unfinished_runs(rb: RobridgeClient) -> list[dict]:
    try:
        return [r for r in rb.list_runs().get("runs", []) if r.get("status") in {"queued", "running"}]
    except Exception:
        return []


def _evaluate_and_submit(client, campaign_id, candidate, artifact_dir, label, suggestion_id, args) -> bool:
    candidate = normalize_candidate(candidate)
    logfire.info("Evaluating candidate", label=label, mode=args.mode)
    outcome = evaluate(
        candidate,
        mode=args.mode,
        artifact_dir=artifact_dir,
        label=label,
        timeout_s=args.run_timeout_s,
        allow_hardware_retry=args.allow_hardware_retry,
    )
    if not outcome.success:
        message = outcome.error or "unknown evaluation failure"
        print(f"ALERT: evaluation failed for {label}: {message}")
        _append_json(artifact_dir / "supervision_summary.jsonl", {"event": "evaluation_failed", "label": label, "run_id": outcome.run_id, "success_counted": False, "error": message, "time": _iso_now()})
        if suggestion_id and not outcome.platform_failure:
            client.update_suggestion_status(suggestion_id, "rejected")
        return False
    if not _valid_outcome(outcome.parameter_values, outcome.objective_values):
        print(f"ALERT: invalid evaluator output for {label}; no BO result submitted.")
        _append_json(artifact_dir / "supervision_summary.jsonl", {"event": "invalid_evaluator_output", "label": label, "run_id": outcome.run_id, "success_counted": False, "time": _iso_now()})
        return False
    row = {
        "parameter_values": outcome.parameter_values,
        "objective_values": outcome.objective_values,
        "metadata": {
            "external_ref": {"system": "roboflex" if args.mode == "robridge-real" else "local-simulation", "id": outcome.run_id or label},
            "notes": "informed seed" if suggestion_id is None else "BO-MCP suggestion",
        },
    }
    if suggestion_id:
        row["suggestion_id"] = suggestion_id
    key = BoMcpClient.make_idempotency_key("result", campaign_id, label)
    client.submit_results(campaign_id, results=[row], idempotency_key=key, force=bool(suggestion_id))
    _append_json(artifact_dir / "submitted_results.jsonl", row)
    _append_json(artifact_dir / "supervision_summary.jsonl", {"event": "experiment_analyzed", "label": label, "run_id": outcome.run_id, "success_counted": True, "yield_percent": outcome.objective_values["yield_percent"], "green_score": outcome.objective_values["green_score"], "time": _iso_now()})
    print(f"Submitted {label}: yield={outcome.objective_values['yield_percent']:.1f}, green={outcome.objective_values['green_score']:.1f}")
    return True


def _valid_outcome(parameters: dict | None, objectives: dict | None) -> bool:
    if not parameters or not objectives:
        return False
    needed = {"yield_percent", "green_score"}
    if set(objectives) != needed:
        return False
    return all(isinstance(v, int | float) and math.isfinite(float(v)) for v in objectives.values())


def _list_results(client: BoMcpClient, campaign_id: str) -> list[dict]:
    return client._json_request("GET", f"/api/v1/results/{campaign_id}")


def _export(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
        (artifact_dir / "bo_campaign_export.csv").write_bytes(content)
        (artifact_dir / "bo_campaign_export.content_type.txt").write_text(content_type)
    except Exception as exc:
        print(f"Export skipped: {exc}")


def _finish(client: BoMcpClient, campaign_id: str, args: argparse.Namespace) -> None:
    if args.terminate_bo_on_exit:
        client.lifecycle(campaign_id, action="terminate")
        print("BO campaign terminated.")
    elif args.pause_bo_on_exit:
        try:
            status = client.get_campaign(campaign_id).get("status")
            if status == "running":
                client.lifecycle(campaign_id, action="pause")
                print("BO campaign paused.")
        except Exception as exc:
            print(f"Pause skipped: {exc}")


def _label(base: str, retry_suffix: str | None) -> str:
    return f"{base}_{retry_suffix}" if retry_suffix else base


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, payload) -> None:
    with path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
