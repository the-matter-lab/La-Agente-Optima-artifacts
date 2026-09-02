from __future__ import annotations

import csv
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .evaluation import RESULT_COLUMNS, evaluate_candidate, run_pyscf_smoke
from .intake import OBJECTIVE_NAME, PARAMETER_NAME, build_intake
from .search_space import Candidate, as_lookup, load_candidates


class TeeLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")


def emit(tag: str, message: str, log: TeeLog | None = None) -> None:
    line = f"[{tag}] {message}"
    print(line, flush=True)
    if log:
        log.write(line)


def _extract_campaign_id(response: dict[str, Any]) -> str:
    for key in ("campaign_id", "id"):
        if response.get(key):
            return str(response[key])
    campaign = response.get("campaign")
    if isinstance(campaign, dict):
        for key in ("campaign_id", "id"):
            if campaign.get(key):
                return str(campaign[key])
    raise ValueError(f"Could not find campaign id in create response keys={list(response)}")


def _suggestions_from_response(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("suggestions", "data", "items"):
            value = response.get(key)
            if isinstance(value, list):
                return value
    return []


def _suggestion_id(suggestion: dict[str, Any]) -> str:
    for key in ("suggestion_id", "id"):
        if suggestion.get(key):
            return str(suggestion[key])
    raise ValueError(f"Suggestion has no id: keys={list(suggestion)}")


def _suggestion_key(suggestion: dict[str, Any]) -> str:
    params = suggestion.get("parameter_values") or suggestion.get("parameters") or suggestion.get("candidate") or {}
    if isinstance(params, dict) and params.get(PARAMETER_NAME):
        return str(params[PARAMETER_NAME])
    if suggestion.get(PARAMETER_NAME):
        return str(suggestion[PARAMETER_NAME])
    raise ValueError(f"Suggestion has no {PARAMETER_NAME}: keys={list(suggestion)}")


def _ensure_results_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=RESULT_COLUMNS).writeheader()


def append_result(path: Path, result: dict[str, Any]) -> None:
    _ensure_results_csv(path)
    row = {column: result.get(column) for column in RESULT_COLUMNS}
    if row.get("error_message"):
        row["error_message"] = str(row["error_message"]).replace("\n", " | ")
    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=RESULT_COLUMNS).writerow(row)


def write_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _campaign_status(client: BoMcpClient, campaign_id: str) -> str:
    try:
        campaign = client.get_campaign(campaign_id)
        if campaign.get("status"):
            return str(campaign["status"])
        if isinstance(campaign.get("campaign"), dict) and campaign["campaign"].get("status"):
            return str(campaign["campaign"]["status"])
    except Exception:
        return "unknown"
    return "unknown"


def _maybe_resume(client: BoMcpClient, campaign_id: str, log: TeeLog) -> None:
    status = _campaign_status(client, campaign_id)
    if status == "paused":
        emit("EVENT", f"resuming paused campaign_id={campaign_id}", log)
        client.lifecycle(campaign_id, action="resume")
    elif status == "completed":
        emit("EVENT", f"reopening completed campaign_id={campaign_id}", log)
        client.lifecycle(campaign_id, action="reopen")
    else:
        emit("EVENT", f"using campaign_id={campaign_id} status={status}", log)


def _pause_if_running(client: BoMcpClient, campaign_id: str, log: TeeLog) -> None:
    status = _campaign_status(client, campaign_id)
    if status == "running":
        try:
            client.lifecycle(campaign_id, action="pause")
            emit("EVENT", f"paused campaign_id={campaign_id}", log)
        except Exception as exc:
            emit("ALERT", f"pause failed campaign_id={campaign_id}: {type(exc).__name__}: {exc}", log)
    else:
        emit("EVENT", f"skip pause campaign_id={campaign_id} status={status}", log)


def _export(client: BoMcpClient, campaign_id: str, artifact_dir: Path, log: TeeLog) -> None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
        path = artifact_dir / "bo_export.csv"
        path.write_bytes(content)
        emit("EVENT", f"exported campaign CSV path={path} content_type={content_type}", log)
    except Exception as exc:
        emit("ALERT", f"campaign export skipped: {type(exc).__name__}: {exc}", log)


def _write_report(results_csv: Path, report_path: Path) -> None:
    if not results_csv.exists():
        return
    rows: list[dict[str, str]] = []
    with results_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    successes = [row for row in rows if row.get("status") == "success" and row.get("objective") not in (None, "")]
    lines = ["# Pollice 2021 BO invocation report", ""]
    if successes:
        best = max(successes, key=lambda row: float(row["objective"]))
        lines += [
            f"Best molecule_key: {best.get('molecule_key')}",
            f"Best smiles_canonical: {best.get('smiles_canonical')}",
            f"Best delta_est_ev: {best.get('delta_est_ev')}",
            f"Best objective: {best.get('objective')}",
            f"Best n_conformers_generated: {best.get('n_conformers_generated')}",
            f"Best oscillator_strength: {best.get('oscillator_strength')}",
            "",
        ]
    lines += [f"Evaluated rows in this artifact CSV: {len(rows)}", "", "See evaluation_results.csv for the full table.", ""]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _submit_success(
    client: BoMcpClient,
    campaign_id: str,
    suggestion_id: str,
    result: dict[str, Any],
    run_nonce: str,
) -> dict[str, Any]:
    return client.submit_results(
        campaign_id,
        results=[
            {
                "suggestion_id": suggestion_id,
                "parameter_values": {PARAMETER_NAME: result["molecule_key"]},
                "objective_values": {OBJECTIVE_NAME: float(result["objective"])},
                "metadata": {
                    "notes": f"CREST lowest-conformer TD-DFT gap evaluation for {result['molecule_key']}",
                    "conditions": {
                        "n_conformers_generated": result.get("n_conformers_generated"),
                        "crest_wall_s": result.get("crest_wall_s"),
                        "pyscf_wall_s": result.get("pyscf_wall_s"),
                        "total_eval_wall_s": result.get("total_eval_wall_s"),
                    },
                },
            }
        ],
        idempotency_key=BoMcpClient.make_idempotency_key("pollice-result", campaign_id, suggestion_id, run_nonce),
        force=True,
    )


def run_campaign(args: Any) -> int:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "worker_logs").mkdir(parents=True, exist_ok=True)
    log = TeeLog(artifact_dir / "run.log")
    results_csv = artifact_dir / "evaluation_results.csv"
    _ensure_results_csv(results_csv)

    if args.pyscf_smoke_only:
        emit("EVENT", "starting PySCF smoke test only; no BO campaign will be touched", log)
        result = run_pyscf_smoke(timeout_s=args.pyscf_smoke_timeout_s, log_path=str(artifact_dir / "pyscf_smoke_raw.log"))
        emit("RESULT", f"pyscf_smoke status=success delta={result['delta_est_ev']:.6g} objective={result['objective']:.6g} wall_s={result['wall_s']:.1f}", log)
        return 0

    candidates = load_candidates(
        args.csv_path,
        heavy_atom_cutoff=args.heavy_atom_cutoff,
        limit=args.limit_candidates,
        fingerprint_components=args.fingerprint_components,
        random_seed=args.random_seed,
    )
    lookup = as_lookup(candidates)
    emit("EVENT", f"loaded candidates n={len(candidates)} heavy_atom_cutoff=<{args.heavy_atom_cutoff} csv={args.csv_path}", log)

    intake = build_intake(
        candidates,
        batch_size=args.batch_size,
        initial_design_size=min(args.initial_design_size, max(1, len(candidates) - 1)),
        random_seed=args.random_seed,
    )
    (artifact_dir / "campaign_intake.json").write_text(json.dumps(intake, indent=2), encoding="utf-8")

    client = BoMcpClient.from_env(timeout_s=args.client_timeout_s)
    run_nonce = args.run_nonce or uuid.uuid4().hex[:10]
    campaign_id = args.campaign_id
    if campaign_id:
        _maybe_resume(client, campaign_id, log)
    else:
        validation = client.validate_intake(intake)
        if not validation.get("valid", False):
            emit("ALERT", f"intake validation failed errors={validation.get('errors')}", log)
            return 2
        emit("EVENT", "intake validation succeeded", log)
        created = client.create_campaign(
            intake,
            idempotency_key=BoMcpClient.make_idempotency_key("pollice-create", run_nonce),
        )
        campaign_id = _extract_campaign_id(created)
        emit("EVENT", f"created campaign_id={campaign_id}", log)

    started = time.monotonic()
    completed_loops = 0
    last_heartbeat = started
    try:
        while completed_loops < args.max_iterations:
            if Path(args.stop_file).exists():
                emit("EVENT", f"stop file detected path={args.stop_file}; removing marker and stopping before suggestion generation", log)
                Path(args.stop_file).unlink(missing_ok=True)
                break

            now = time.monotonic()
            if now - last_heartbeat >= args.heartbeat_s:
                emit("HEARTBEAT", f"campaign_id={campaign_id} elapsed_s={now - started:.0f} completed_invocation_loops={completed_loops}", log)
                last_heartbeat = now

            pending = client.query_suggestions(campaign_id, status_filter="pending", limit=args.batch_size)
            suggestions = pending[: args.batch_size]
            if suggestions:
                emit("EVENT", f"reusing pending suggestions n={len(suggestions)}", log)
            else:
                decision = client.next_action(campaign_id)
                action = decision.get("action")
                if action != "bo_generate_suggestions":
                    emit("EVENT", f"server next_action={action}; stopping invocation", log)
                    break
                try:
                    response = client.generate_suggestions(campaign_id, batch_size=args.batch_size, timeout_s=args.suggestion_timeout_s)
                except BoMcpOperationError as exc:
                    emit("ALERT", f"suggestion generation stopped: {exc}", log)
                    break
                suggestions = _suggestions_from_response(response)
                emit("EVENT", f"generated suggestions n={len(suggestions)}", log)

            if not suggestions:
                emit("ALERT", "no suggestions available; stopping invocation", log)
                break

            futures = {}
            with ThreadPoolExecutor(max_workers=max(1, min(args.batch_size, len(suggestions)))) as pool:
                for suggestion in suggestions:
                    sid = _suggestion_id(suggestion)
                    key = _suggestion_key(suggestion)
                    candidate = lookup[key]
                    futures[pool.submit(
                        evaluate_candidate,
                        candidate,
                        synthetic=args.synthetic_evaluator,
                        eval_timeout_s=args.eval_timeout_s,
                        pyscf_timeout_s=args.pyscf_timeout_s,
                        crest_threads=args.crest_threads,
                        child_log_path=str(artifact_dir / "worker_logs" / f"{key}_{sid}.log"),
                    )] = (sid, key)
                for future in as_completed(futures):
                    sid, key = futures[future]
                    result = future.result()
                    append_result(results_csv, result)
                    write_jsonl(artifact_dir / "evaluation_results.jsonl", result)
                    if result.get("status") == "success":
                        _submit_success(client, campaign_id, sid, result, run_nonce)
                        emit("RESULT", f"molecule_key={key} status=success objective={result['objective']:.8g} delta_est_ev={result['delta_est_ev']:.8g} S1_ev={result['S1_ev']:.8g} T1_ev={result['T1_ev']:.8g}", log)
                    else:
                        client.update_suggestion_status(sid, "rejected")
                        message = str(result.get("error_message", ""))[:200].replace("\n", " ")
                        emit("RESULT", f"molecule_key={key} status=failed rejected_suggestion_id={sid} error={message}", log)
            completed_loops += 1
            time.sleep(args.poll_s)
    except (BoMcpClientError, KeyError, ValueError) as exc:
        emit("ALERT", f"campaign invocation error: {type(exc).__name__}: {exc}", log)
        return 3
    finally:
        _export(client, campaign_id, artifact_dir, log)
        _write_report(results_csv, artifact_dir / "invocation_report.md")
        if args.terminate_on_exit:
            try:
                client.lifecycle(campaign_id, action="terminate")
                emit("EVENT", f"terminated smoke-test campaign_id={campaign_id}", log)
            except Exception as exc:
                emit("ALERT", f"terminate failed campaign_id={campaign_id}: {type(exc).__name__}: {exc}", log)
        else:
            _pause_if_running(client, campaign_id, log)
        emit("EVENT", f"artifacts_dir={artifact_dir} results_csv={results_csv} campaign_id={campaign_id}", log)
    return 0
