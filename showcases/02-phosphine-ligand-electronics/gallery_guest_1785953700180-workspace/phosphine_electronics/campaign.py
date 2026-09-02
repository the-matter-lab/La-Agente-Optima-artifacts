from __future__ import annotations

import csv
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import logfire

from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate
from .intake import build_intake
from .reporting import append_jsonl, write_report
from .space import candidate_index, choose_warm_start, load_candidates, warm_start_rationale


def tag(kind: str, message: str) -> None:
    print(f"[{kind}] {message}", flush=True)


def _setup_logger(artifact_dir: Path) -> logging.Logger:
    logger = logging.getLogger("phosphine_electronics")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(artifact_dir / "run.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    return logger


def _status(campaign: dict) -> str:
    data = campaign.get("campaign") if isinstance(campaign.get("campaign"), dict) else campaign
    return str(data.get("status") or data.get("state") or "").lower()


def _result_candidate_ids(results: list[dict]) -> set[str]:
    ids = set()
    for r in results:
        pv = r.get("parameter_values") or r.get("parameters") or {}
        cid = pv.get("candidate_id")
        if cid:
            ids.add(str(cid))
    return ids


def _bo_result_count(results: list[dict]) -> int:
    return sum(1 for r in results if r.get("suggestion_id"))


def _suggestion_candidate_id(s: dict) -> str | None:
    return (s.get("parameter_values") or {}).get("candidate_id")


def _evaluation_record(row: dict, ev, phase: str, suggestion_id: str | None = None, rationale: str | None = None) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "suggestion_id": suggestion_id,
        "candidate_id": row["candidate_id"],
        "R1": row["R1"],
        "R2": row["R2"],
        "R3": row["R3"],
        "ligand_smiles": row["ligand_smiles"],
        "status": ev.status,
        "descriptors": ev.descriptors,
        "objectives": ev.objectives,
        "proxies": ev.proxies,
        "elapsed_s": ev.elapsed_s,
        "error": ev.error,
        "rationale": rationale,
    }


def _submit_successes(client: BoMcpClient, campaign_id: str, records: list[dict], *, phase: str, run_nonce: str) -> None:
    payload = []
    for r in records:
        if r["status"] != "success":
            continue
        notes = f"phase={phase}; candidate_id={r['candidate_id']}; descriptors/proxies stored in artifact JSONL"
        payload.append(
            {
                "parameter_values": {"candidate_id": r["candidate_id"]},
                "objective_values": {k: float(v) for k, v in r["objectives"].items()},
                "suggestion_id": r.get("suggestion_id"),
                "metadata": {"notes": notes, "conditions": {"phase": phase, "synthetic": "synthetic" in str(r.get("proxies", {}))}},
            }
        )
    if payload:
        key = BoMcpClient.make_idempotency_key("phosphine-result", campaign_id, phase, run_nonce, str(len(payload)), uuid4().hex[:8])
        client.submit_results(campaign_id, results=payload, idempotency_key=key, force=False)


def _evaluate_many(rows: list[dict], args, logger: logging.Logger) -> list[tuple[dict, object]]:
    out = []
    workers = max(1, int(args.eval_workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                evaluate,
                row,
                synthetic=args.synthetic_evaluator,
                timeout_s=args.pyscf_timeout_s,
                geometry_max_steps=args.geometry_max_steps,
            ): row
            for row in rows
        }
        for fut in as_completed(futs):
            row = futs[fut]
            ev = fut.result()
            logger.info("evaluation %s %s %.1fs", row["candidate_id"], ev.status, ev.elapsed_s)
            out.append((row, ev))
    return out


def _write_warm_start(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["candidate_id", "R1", "R2", "R3", "ligand_smiles", "rationale"])
        w.writeheader()
        for row in rows:
            w.writerow({**row, "rationale": warm_start_rationale(row)})


def _maybe_lifecycle(client: BoMcpClient, campaign_id: str, action: str, logger: logging.Logger) -> None:
    try:
        client.lifecycle(campaign_id, action=action)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lifecycle %s failed: %s", action, exc)


def _ensure_active_for_resume(client: BoMcpClient, campaign_id: str, logger: logging.Logger) -> None:
    status = _status(client.get_campaign(campaign_id))
    if status == "paused":
        tag("EVENT", f"Resuming paused campaign {campaign_id}")
        _maybe_lifecycle(client, campaign_id, "resume", logger)
    elif status == "completed":
        tag("EVENT", f"Reopening completed campaign {campaign_id}")
        _maybe_lifecycle(client, campaign_id, "reopen", logger)
    else:
        tag("EVENT", f"Using campaign {campaign_id} status={status or 'unknown'}")


def _pending_or_generate(client: BoMcpClient, campaign_id: str, batch_size: int, timeout_s: float, logger: logging.Logger) -> list[dict]:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=100)
    if pending:
        return pending[:batch_size]
    decision = client.next_action(campaign_id)
    action = str(decision.get("action") or "")
    logger.info("next_action %s", decision)
    if action and action != "bo_generate_suggestions":
        tag("ALERT", f"BO-MCP next_action={action}; stopping invocation")
        return []
    try:
        resp = client.generate_suggestions(campaign_id, batch_size=batch_size, timeout_s=timeout_s)
    except Exception as exc:  # noqa: BLE001
        tag("ALERT", f"Suggestion generation stopped: {str(exc).splitlines()[0]}")
        return []
    if not resp.get("success", True):
        tag("ALERT", f"Suggestion generation returned no candidates: {resp.get('errors')}")
        return []
    return list(resp.get("suggestions") or [])


def run(args) -> str:
    run_nonce = uuid4().hex[:10]
    artifact_dir = Path(args.artifact_dir or (Path("artifacts") / f"phosphine_electronics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    logger = _setup_logger(artifact_dir)
    logfire.info("starting phosphine campaign", artifact_dir=str(artifact_dir))
    rows = load_candidates()
    index = candidate_index()
    records_path = artifact_dir / "evaluation_records.jsonl"
    tag("EVENT", f"Artifacts: {artifact_dir}")
    tag("EVENT", f"Loaded {len(rows)} pre-enumerated ligand candidates")

    if args.pyscf_smoke_only:
        row = index.get(args.pyscf_smoke_candidate) or rows[0]
        tag("EVENT", f"Running PySCF smoke evaluation for {row['candidate_id']}")
        ev = evaluate(row, synthetic=False, timeout_s=args.pyscf_timeout_s, geometry_max_steps=args.geometry_max_steps)
        append_jsonl(records_path, _evaluation_record(row, ev, "pyscf_smoke"))
        if ev.status == "success":
            tag("RESULT", f"PySCF smoke success {row['candidate_id']} HOMO={ev.descriptors['homo_energy_eV']:.3f} gap={ev.descriptors['homo_lumo_gap_eV']:.3f}")
        else:
            tag("ALERT", f"PySCF smoke failed {row['candidate_id']}: {ev.error}")
        return ""

    client = BoMcpClient.from_env(timeout_s=args.client_timeout_s)
    if args.campaign_id:
        campaign_id = args.campaign_id
        _ensure_active_for_resume(client, campaign_id, logger)
    else:
        intake = build_intake(args.campaign_name, batch_size=args.batch_size)
        validation = client.validate_intake(intake)
        if not validation.get("valid", False):
            raise RuntimeError(f"Campaign intake invalid: {validation}")
        key = BoMcpClient.make_idempotency_key("phosphine-create", args.campaign_name, run_nonce)
        created = client.create_campaign(intake, idempotency_key=key)
        campaign_id = str(created.get("campaign_id") or created.get("id") or (created.get("campaign") or {}).get("campaign_id"))
        tag("EVENT", f"Created campaign {campaign_id}")
    (artifact_dir / "campaign_id.txt").write_text(campaign_id + "\n")

    results = client.get_results(campaign_id)
    completed = _result_candidate_ids(results)
    if not completed:
        warm_rows = [r for r in choose_warm_start(rows, args.warm_start_size) if r["candidate_id"] not in completed]
        _write_warm_start(artifact_dir / "warm_start_rationale.csv", warm_rows)
        tag("EVENT", f"Evaluating {len(warm_rows)} script-selected warm-start ligands")
        seed_records = []
        for row, ev in _evaluate_many(warm_rows, args, logger):
            rec = _evaluation_record(row, ev, "warm_start", rationale=warm_start_rationale(row))
            append_jsonl(records_path, rec)
            seed_records.append(rec)
            if ev.status == "success":
                tag("RESULT", f"warm_start {row['candidate_id']} HOMOerr={ev.objectives['donor_homo_error']:.3f} gaperr={ev.objectives['gap_error']:.3f} steric={ev.objectives['steric_excess']:.1f} heavy={ev.objectives['heavy_atom_count']:.0f}")
            else:
                tag("ALERT", f"warm_start {row['candidate_id']} failed: {ev.error}")
        _submit_successes(client, campaign_id, seed_records, phase="warm_start", run_nonce=run_nonce)
    else:
        tag("EVENT", f"Campaign already has {len(completed)} completed candidate ids; skipping warm start")

    last_heartbeat = time.time()
    bo_batches_done = 0
    while bo_batches_done < args.max_bo_batches:
        if Path(args.stop_file).exists():
            tag("EVENT", f"Stop file {args.stop_file} found before suggestion generation; deleting marker and exiting")
            Path(args.stop_file).unlink(missing_ok=True)
            break
        if time.time() - last_heartbeat >= args.heartbeat_s:
            tag("HEARTBEAT", f"campaign_id={campaign_id} artifact_dir={artifact_dir}")
            last_heartbeat = time.time()
        results = client.get_results(campaign_id)
        if _bo_result_count(results) >= args.max_bo_batches * args.batch_size:
            tag("EVENT", "Configured BO-guided evaluation budget already reached")
            break
        completed = _result_candidate_ids(results)
        all_sugs = client.query_suggestions(campaign_id, status_filter=None, limit=500)
        rejected_or_failed = {str(_suggestion_candidate_id(s)) for s in all_sugs if str(s.get("status", "")).lower() in {"rejected", "failed"} and _suggestion_candidate_id(s)}
        suggestions = _pending_or_generate(client, campaign_id, args.batch_size, args.suggestion_timeout_s, logger)
        if not suggestions:
            break
        eval_rows, usable_sugs = [], []
        for s in suggestions[: args.batch_size]:
            cid = _suggestion_candidate_id(s)
            sid = s.get("suggestion_id")
            if not cid or cid not in index:
                tag("ALERT", f"Rejecting suggestion {sid}: missing/unknown candidate_id={cid}")
                client.update_suggestion_status(sid, "rejected")
                continue
            if cid in completed or cid in rejected_or_failed:
                tag("ALERT", f"Rejecting duplicate/non-actionable suggestion {sid} candidate_id={cid}")
                client.update_suggestion_status(sid, "rejected")
                continue
            eval_rows.append(index[cid]); usable_sugs.append(s)
        if not eval_rows:
            continue
        tag("EVENT", f"Evaluating BO batch of {len(eval_rows)} ligand(s)")
        bo_records = []
        by_cid = {r["candidate_id"]: s for r, s in zip(eval_rows, usable_sugs)}
        for row, ev in _evaluate_many(eval_rows, args, logger):
            sid = by_cid[row["candidate_id"]].get("suggestion_id")
            rec = _evaluation_record(row, ev, "bo", suggestion_id=sid)
            append_jsonl(records_path, rec)
            bo_records.append(rec)
            if ev.status == "success":
                tag("RESULT", f"bo {row['candidate_id']} HOMOerr={ev.objectives['donor_homo_error']:.3f} gaperr={ev.objectives['gap_error']:.3f} steric={ev.objectives['steric_excess']:.1f} heavy={ev.objectives['heavy_atom_count']:.0f}")
            else:
                tag("ALERT", f"bo {row['candidate_id']} failed: {ev.error}")
                client.update_suggestion_status(sid, "rejected")
        _submit_successes(client, campaign_id, bo_records, phase="bo", run_nonce=run_nonce)
        bo_batches_done += 1
        time.sleep(max(0.0, float(args.poll_s)))

    try:
        raw, content_type = client.export_campaign(campaign_id, fmt="csv")
        (artifact_dir / "bo_mcp_export.csv").write_bytes(raw)
        logger.info("exported campaign content_type=%s bytes=%d", content_type, len(raw))
    except Exception as exc:  # noqa: BLE001
        tag("ALERT", f"Final export skipped: {str(exc).splitlines()[0]}")
    write_report(records_path, artifact_dir / "report.md", artifact_dir / "report.csv")
    status = _status(client.get_campaign(campaign_id))
    if args.terminate_on_exit:
        _maybe_lifecycle(client, campaign_id, "terminate", logger)
        tag("EVENT", f"Terminated campaign {campaign_id}")
    elif status == "running":
        _maybe_lifecycle(client, campaign_id, "pause", logger)
        tag("EVENT", f"Paused campaign {campaign_id}; resume with --campaign-id {campaign_id}")
    else:
        tag("EVENT", f"Leaving campaign {campaign_id} status={status or 'unknown'}")
    tag("EVENT", f"Report: {artifact_dir / 'report.md'}")
    return campaign_id
