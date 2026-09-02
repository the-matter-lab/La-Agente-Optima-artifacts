from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .evaluation import InfrastructureEvaluationError, evaluate_candidate, run_estructural_workspace_preflight, run_pyscf_literal_xyz_preflight
from .intake import build_intake
from .library import WARM_START_CANDIDATE_IDS, library_by_id
from .reporting import append_jsonl, print_tag, report_library


def _campaign_id(resp: dict) -> str:
    cid = resp.get("campaign_id") or resp.get("id")
    if not cid:
        raise RuntimeError(f"Campaign create response did not include campaign_id: {resp}")
    return str(cid)


def _campaign_status(client: BoMcpClient, campaign_id: str) -> str:
    try:
        payload = client.get_campaign(campaign_id)
    except Exception:
        return "unknown"
    for key in ("status", "state"):
        if key in payload:
            return str(payload[key]).lower()
    campaign = payload.get("campaign") if isinstance(payload, dict) else None
    if isinstance(campaign, dict):
        for key in ("status", "state"):
            if key in campaign:
                return str(campaign[key]).lower()
    return "unknown"


def _suggestions_from_payload(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("suggestions", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if "parameter_values" in payload or "parameters" in payload:
            return [payload]
    return []


def _candidate_id_from_suggestion(suggestion: dict) -> str:
    params = suggestion.get("parameter_values") or suggestion.get("parameters") or suggestion.get("candidate") or {}
    if isinstance(params, dict) and "candidate_id" in params:
        return str(params["candidate_id"])
    if "candidate_id" in suggestion:
        return str(suggestion["candidate_id"])
    raise RuntimeError(f"Could not find candidate_id in suggestion: {suggestion}")


def _suggestion_id(suggestion: dict) -> str | None:
    for key in ("suggestion_id", "id"):
        if suggestion.get(key):
            return str(suggestion[key])
    return None


def _next_action_value(decision: dict) -> str:
    return str(decision.get("action") or decision.get("next_action") or "").lower()


def _maybe_resume(client: BoMcpClient, campaign_id: str) -> None:
    status = _campaign_status(client, campaign_id)
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        print_tag("EVENT", f"resumed campaign {campaign_id}")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        print_tag("EVENT", f"reopened completed campaign {campaign_id}")


def _pending_or_generate(client: BoMcpClient, campaign_id: str, batch_size: int, timeout_s: float) -> list[dict]:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=batch_size)
    if pending:
        print_tag("EVENT", f"reusing {len(pending[:batch_size])} pending suggestion(s)")
        return pending[:batch_size]
    payload = client.generate_suggestions(campaign_id, batch_size=batch_size, timeout_s=timeout_s)
    suggestions = _suggestions_from_payload(payload)
    if not suggestions:
        raise RuntimeError(f"No suggestions returned: {payload}")
    return suggestions


def _export(client: BoMcpClient, campaign_id: str, artifacts_dir: Path) -> None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
        path = artifacts_dir / "campaign_export.csv"
        path.write_bytes(content)
        (artifacts_dir / "campaign_export.content_type.txt").write_text(content_type, encoding="utf-8")
        print_tag("EVENT", f"exported campaign CSV to {path.as_posix()}")
    except Exception as exc:
        print_tag("ALERT", f"campaign export skipped after non-critical error: {exc}")


def _consume_stop_file(stop_file: str, campaign_id: str, where: str) -> bool:
    path = Path(stop_file)
    if path.exists():
        path.unlink()
        print_tag("EVENT", f"stop file observed and removed {where}; exiting campaign {campaign_id}")
        return True
    return False


def _preflight_estructural_connectivity(timeout_s: float = 3.0) -> None:
    url = os.getenv("ESTRUCTURAL_A2A_URL") or "http://a2a:8033"
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        raise RuntimeError(f"Invalid ESTRUCTURAL_A2A_URL={url!r}; expected URL such as http://a2a:8033")
    socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    with socket.create_connection((host, port), timeout=timeout_s):
        pass
    print_tag("EVENT", f"Estructural connectivity preflight OK: {url}")


def _production_preflight(args, artifacts_dir: Path) -> bool:
    if args.mock_evaluator or not args.run_calculations or args.create_only or args.library_only:
        return True
    try:
        _preflight_estructural_connectivity(timeout_s=args.preflight_timeout_s)
        preflight_xyz = run_estructural_workspace_preflight(artifacts_dir)
        print_tag("EVENT", "Estructural workspace write preflight OK")
        run_pyscf_literal_xyz_preflight(preflight_xyz, artifacts_dir, timeout_s=min(float(args.workflow_timeout_s), 120.0))
        print_tag("EVENT", "PySCF literal XYZ handoff preflight OK")
    except Exception as exc:
        print_tag(
            "ALERT",
            "production preflight failed before campaign/evaluation submission: "
            f"Estructural/PySCF is not ready for workspace XYZ generation and literal handoff ({exc}). Check ESTRUCTURAL_A2A_URL and GRAPHCHAT_ROOM; in this Docker network the endpoint default is http://a2a:8033 and the room should match the workspace.",
        )
        return False
    return True


def _result_candidate_ids(client: BoMcpClient, campaign_id: str) -> set[str]:
    ids: set[str] = set()
    try:
        rows = client.get_results(campaign_id)
    except Exception as exc:
        print_tag("ALERT", f"could not inspect existing results before warm start: {exc}")
        return ids
    for row in rows:
        params = row.get("parameter_values") or row.get("parameters") or {}
        if isinstance(params, dict) and params.get("candidate_id"):
            ids.add(str(params["candidate_id"]))
    return ids


def _submit_evaluation(
    client: BoMcpClient,
    campaign_id: str,
    candidate,
    record: dict,
    args,
    *,
    suggestion_id: str | None,
    phase: str,
) -> None:
    result_row = {
        "parameter_values": {"candidate_id": candidate.candidate_id},
        "objective_values": {k: float(v) for k, v in record["objectives"].items()},
        "metadata": {
            "notes": f"phase={phase}; feasible={record.get('feasible')}; mode={record.get('mode')}",
            "conditions": {
                "mock_evaluator": bool(args.mock_evaluator),
                "charge": int(args.charge),
                "spin_multiplicity": int(args.spin_multiplicity),
                "phase_warm_start": phase == "warm_start",
            },
        },
    }
    if suggestion_id:
        result_row["suggestion_id"] = suggestion_id
    submit_key = BoMcpClient.make_idempotency_key(
        "result",
        campaign_id,
        phase,
        suggestion_id or candidate.candidate_id,
        uuid.uuid4().hex[:8],
    )
    client.submit_results(campaign_id, results=[result_row], idempotency_key=submit_key, force=True)
    print_tag(
        "RESULT",
        f"phase={phase} candidate={candidate.candidate_id} feasible={record.get('feasible')} "
        f"objectives={json.dumps(result_row['objective_values'], sort_keys=True)}",
    )


def _evaluate_and_submit(client: BoMcpClient, campaign_id: str, candidate, args, artifacts_dir: Path, *, phase: str, suggestion_id: str | None = None) -> dict:
    print_tag("EVENT", f"evaluating {phase} candidate {candidate.candidate_id} ({candidate.ligand_label})")
    record = evaluate_candidate(
        candidate,
        artifacts_dir,
        mock=args.mock_evaluator,
        charge=args.charge,
        spin_multiplicity=args.spin_multiplicity,
        basis_set=args.basis_set,
        xc_functional=args.xc_functional,
        geometry_max_steps=args.geometry_max_steps,
        workflow_timeout_s=args.workflow_timeout_s,
    )
    append_jsonl(artifacts_dir / "evaluations.jsonl", {"phase": phase, **record})
    _submit_evaluation(client, campaign_id, candidate, record, args, suggestion_id=suggestion_id, phase=phase)
    return record


def _run_warm_starts(client: BoMcpClient, campaign_id: str, library: dict, args, artifacts_dir: Path) -> int:
    if not args.hood_warm_start_bo10:
        return 0
    warm_ids = list(WARM_START_CANDIDATE_IDS)
    existing = _result_candidate_ids(client, campaign_id)
    (artifacts_dir / "warm_start_candidates.json").write_text(
        json.dumps([library[cid].asdict() for cid in warm_ids], indent=2),
        encoding="utf-8",
    )
    print_tag("EVENT", f"warm-start preset enabled: exactly 4 candidates={warm_ids}; default_bo_iterations=10")
    completed = 0
    for cid in warm_ids:
        if _consume_stop_file(args.stop_file, campaign_id, "during warm-start phase"):
            setattr(args, "_stop_requested", True)
            break
        if cid in existing:
            print_tag("EVENT", f"warm-start candidate already present on campaign; skipping duplicate submission: {cid}")
            completed += 1
            continue
        _evaluate_and_submit(client, campaign_id, library[cid], args, artifacts_dir, phase="warm_start")
        completed += 1
    return completed


def run(args) -> str | None:
    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_library(artifacts_dir)
    if args.library_only or (not args.run_calculations and not args.mock_evaluator and not args.create_only):
        print_tag("EVENT", "library-only dry run complete; no BO suggestions or calculations started")
        return None

    if not _production_preflight(args, artifacts_dir):
        return None

    library = library_by_id()
    client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    campaign_id = args.campaign_id
    if campaign_id:
        _maybe_resume(client, campaign_id)
    else:
        intake = build_intake(args.campaign_name, random_seed=args.random_seed, batch_size=args.batch_size)
        client.validate_intake(intake)
        create_key = BoMcpClient.make_idempotency_key("create", args.campaign_name, uuid.uuid4().hex[:10])
        resp = client.create_campaign(intake, idempotency_key=create_key)
        campaign_id = _campaign_id(resp)
        print_tag("EVENT", f"created campaign {campaign_id}")
    (artifacts_dir / "campaign_id.txt").write_text(campaign_id, encoding="utf-8")

    if args.create_only:
        print_tag("EVENT", f"create-only complete for campaign {campaign_id}; no suggestions or calculations started")
        return campaign_id

    if args.hood_warm_start_bo10:
        try:
            warm_completed = _run_warm_starts(client, campaign_id, library, args, artifacts_dir)
        except InfrastructureEvaluationError as exc:
            print_tag("ALERT", f"infrastructure failure during warm-start evaluation; no penalized result submitted for failed candidate: {exc}")
            warm_completed = 0
            bo_target = 0
        else:
            bo_target = args.bo_iterations if args.bo_iterations is not None else 10
            if getattr(args, "_stop_requested", False) or _consume_stop_file(args.stop_file, campaign_id, "after warm-start phase before BO suggestion generation"):
                bo_target = 0
            print_tag("EVENT", f"warm-start phase complete: completed_or_existing={warm_completed}/4; BO-selected target this invocation={bo_target}")
    else:
        warm_completed = 0
        bo_target = args.max_successes

    successes = 0
    last_heartbeat = time.time()
    while successes < bo_target:
        if _consume_stop_file(args.stop_file, campaign_id, "before suggestion generation"):
            break
        now = time.time()
        if now - last_heartbeat >= args.heartbeat_s:
            print_tag("HEARTBEAT", f"campaign={campaign_id} warm_starts={warm_completed}/4 bo_completed_this_invocation={successes}/{bo_target}")
            last_heartbeat = now
        decision = client.next_action(campaign_id)
        action = _next_action_value(decision)
        if action and action != "bo_generate_suggestions":
            print_tag("EVENT", f"BO-MCP next_action={action}; stopping invocation")
            break
        try:
            suggestions = _pending_or_generate(client, campaign_id, args.batch_size, args.suggestion_timeout_s)
        except BoMcpOperationError as exc:
            print_tag("EVENT", f"suggestion generation stopped by BO-MCP: {exc}")
            break
        for suggestion in suggestions:
            cid = _candidate_id_from_suggestion(suggestion)
            sid = _suggestion_id(suggestion)
            if cid not in library:
                if sid:
                    client.update_suggestion_status(sid, "rejected")
                print_tag("ALERT", f"rejected unknown candidate_id from BO-MCP: {cid}")
                continue
            try:
                _evaluate_and_submit(client, campaign_id, library[cid], args, artifacts_dir, phase="bo", suggestion_id=sid)
            except InfrastructureEvaluationError as exc:
                print_tag("ALERT", f"infrastructure failure during BO evaluation; pending suggestion left unsubmitted for retry: {exc}")
                bo_target = successes
                break
            successes += 1
            if successes >= bo_target:
                break
        if successes < bo_target:
            time.sleep(max(0.0, float(args.poll_s)))

    _export(client, campaign_id, artifacts_dir)
    if args.terminate_on_exit:
        client.lifecycle(campaign_id, action="terminate")
        print_tag("EVENT", f"terminated campaign {campaign_id}")
    else:
        status = _campaign_status(client, campaign_id)
        if status == "running":
            client.lifecycle(campaign_id, action="pause")
            print_tag("EVENT", f"paused campaign {campaign_id}")
        else:
            print_tag("EVENT", f"campaign {campaign_id} left in status={status}; no pause sent")
    logfire.info("campaign_invocation_complete", campaign_id=campaign_id, successes=successes)
    return campaign_id
