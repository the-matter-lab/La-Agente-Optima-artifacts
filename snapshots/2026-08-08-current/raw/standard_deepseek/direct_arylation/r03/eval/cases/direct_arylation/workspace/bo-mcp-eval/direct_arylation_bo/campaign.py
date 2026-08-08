"""Campaign orchestration: create/resume, loop, evaluate, submit, report."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from direct_arylation_bo.evaluator import OracleError, evaluate_one
from direct_arylation_bo.intake import build_intake, CAMPAIGN_MARKER
from direct_arylation_bo.objective import extract_objective_values, format_result_line

# ── helpers ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tagged_print(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


# ── campaign lifecycle ─────────────────────────────────────────────────


def _create_or_resume(
    client: BoMcpClient,
    campaign_id: str | None,
    artifact_dir: Path,
) -> str:
    """Create a new campaign or resume an existing one.

    Returns the campaign_id.
    """
    if campaign_id:
        # Resume / reopen existing campaign.
        _tagged_print("EVENT", f"Resuming campaign {campaign_id}")
        try:
            status = client.next_action(campaign_id)
        except BoMcpClientError:
            _tagged_print("ALERT", f"Cannot reach campaign {campaign_id} — exiting.")
            sys.exit(1)

        st = status.get("status", "unknown")
        _tagged_print("EVENT", f"Campaign {campaign_id} status={st}  iteration={status.get('iteration')}  n_results={status.get('n_results')}")

        if st == "paused":
            client.lifecycle(campaign_id, action="resume")
            _tagged_print("EVENT", f"Resumed campaign {campaign_id}")
        elif st == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _tagged_print("EVENT", f"Reopened completed campaign {campaign_id}")
        elif st not in ("running",):
            _tagged_print("ALERT", f"Campaign {campaign_id} is in unexpected state '{st}' — cannot continue.")
            sys.exit(1)

        return campaign_id

    # Create new campaign.
    intake = build_intake()
    _tagged_print("EVENT", f"Validating intake for new campaign '{intake['name']}'")

    try:
        client.validate_intake(intake)
    except BoMcpOperationError as exc:
        _tagged_print("ALERT", f"Intake validation failed: {exc}")
        sys.exit(1)

    idem_key = BoMcpClient.make_idempotency_key("create", intake["name"])
    _tagged_print("EVENT", f"Creating campaign (idempotency_key={idem_key})")

    try:
        resp = client.create_campaign(intake, idempotency_key=idem_key)
    except BoMcpClientError as exc:
        _tagged_print("ALERT", f"Campaign creation failed: {exc}")
        sys.exit(1)

    if not resp.get("success"):
        _tagged_print("ALERT", f"Campaign creation rejected: {resp.get('errors')}")
        sys.exit(1)

    cid = resp["campaign_id"]
    _tagged_print("EVENT", f"Created campaign {cid}")
    _tagged_print("EVENT", f"BO_MCP_CAMPAIGN_ID={cid}")

    # Persist campaign id for resume.
    (artifact_dir / "campaign_id.txt").write_text(cid)
    return cid


# ── main loop ──────────────────────────────────────────────────────────


def run_campaign(
    client: BoMcpClient,
    campaign_id: str | None,
    artifact_dir: Path,
    *,
    max_attempts: int = 60,
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    stop_file: str = "STOP",
) -> str:
    """Run the BO loop until budget exhausted or stopped.

    Returns the campaign_id.
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results_log = artifact_dir / "results.jsonl"
    last_heartbeat = time.monotonic()

    cid = _create_or_resume(client, campaign_id, artifact_dir)

    # Count existing results so we know how many attempts remain.
    existing = client.get_results(cid)
    attempts_done = len(existing)
    _tagged_print("EVENT", f"Campaign {cid}: {attempts_done} results already recorded, budget={max_attempts}")

    if attempts_done >= max_attempts:
        _tagged_print("EVENT", f"Budget already exhausted ({attempts_done} >= {max_attempts}) — nothing to do.")
        _final_report(client, cid, artifact_dir)
        return cid

    while attempts_done < max_attempts:
        # ── stop-file check ──────────────────────────────────────────
        stop_path = Path(stop_file)
        if stop_path.exists():
            _tagged_print("EVENT", f"Stop file '{stop_file}' detected — shutting down.")
            stop_path.unlink(missing_ok=True)
            break

        # ── heartbeat ────────────────────────────────────────────────
        now_m = time.monotonic()
        if now_m - last_heartbeat >= heartbeat_s:
            _tagged_print("HEARTBEAT", f"alive  campaign={cid}  attempts={attempts_done}/{max_attempts}  ts={_now_iso()}")
            last_heartbeat = now_m

        # ── next action ──────────────────────────────────────────────
        try:
            decision = client.next_action(cid)
        except BoMcpClientError as exc:
            _tagged_print("ALERT", f"next_action failed: {exc} — retrying in {poll_s}s")
            time.sleep(poll_s)
            continue

        action = decision.get("action")
        _tagged_print("EVENT", f"next_action → {action}  reason={decision.get('reason','')}  n_results={decision.get('n_results')}")

        if action != "bo_generate_suggestions":
            _tagged_print("EVENT", f"Server says stop (action={action}) — exiting loop.")
            break

        # ── generate suggestion ──────────────────────────────────────
        try:
            gen = client.generate_suggestions(cid, batch_size=1)
        except BoMcpClientError as exc:
            _tagged_print("ALERT", f"generate_suggestions failed: {exc} — retrying in {poll_s}s")
            time.sleep(poll_s)
            continue

        if not gen.get("success"):
            _tagged_print("ALERT", f"Suggestion generation rejected: {gen.get('errors')} — exiting loop.")
            break

        suggestions = gen.get("suggestions") or []
        if not suggestions:
            _tagged_print("EVENT", "No suggestions returned — exiting loop.")
            break

        sug = suggestions[0]
        sid = sug["suggestion_id"]
        params = sug["parameter_values"]

        # ── evaluate ─────────────────────────────────────────────────
        attempts_done += 1
        attempt = attempts_done

        try:
            oracle = evaluate_one(params)
            obj_vals = extract_objective_values(oracle)
            status = "success"
            error_msg = None
        except OracleError as exc:
            obj_vals = None
            status = "failed"
            error_msg = str(exc)

        # ── report ───────────────────────────────────────────────────
        line = format_result_line(attempt, params, status, obj_vals, error_msg)
        _tagged_print("RESULT", line.removeprefix("[RESULT] "))

        # ── persist to results log ───────────────────────────────────
        record = {
            "attempt": attempt,
            "suggestion_id": sid,
            "parameter_values": params,
            "status": status,
            "objective_values": obj_vals,
            "error": error_msg,
            "ts": _now_iso(),
        }
        with open(results_log, "a") as fh:
            fh.write(json.dumps(record) + "\n")

        # ── submit to BO-MCP ─────────────────────────────────────────
        if status == "success" and obj_vals is not None:
            idem_key = BoMcpClient.make_idempotency_key("result", cid, sid)
            try:
                sub = client.submit_results(
                    cid,
                    results=[
                        {
                            "suggestion_id": sid,
                            "parameter_values": params,
                            "objective_values": obj_vals,
                        }
                    ],
                    idempotency_key=idem_key,
                )
                if not sub.get("success"):
                    _tagged_print("ALERT", f"Result submission rejected: {sub.get('errors')}  field_errors={sub.get('field_errors')}")
            except BoMcpClientError as exc:
                _tagged_print("ALERT", f"Result submission failed: {exc}")
        else:
            # Failed evaluation — mark suggestion as rejected so BO-MCP
            # knows it was attempted but failed.
            try:
                client.update_suggestion_status(sid, "rejected")
            except BoMcpClientError as exc:
                _tagged_print("ALERT", f"Failed to reject suggestion {sid}: {exc}")

        # ── poll delay ───────────────────────────────────────────────
        time.sleep(poll_s)

    # ── end of invocation ─────────────────────────────────────────────
    _tagged_print("EVENT", f"Loop finished.  attempts={attempts_done}/{max_attempts}")

    # Pause the campaign (don't terminate) so it can be resumed.
    try:
        status_check = client.next_action(cid)
        st = status_check.get("status", "unknown")
        if st == "running":
            client.lifecycle(cid, action="pause")
            _tagged_print("EVENT", f"Paused campaign {cid}")
    except BoMcpClientError as exc:
        _tagged_print("ALERT", f"Could not pause campaign: {exc}")

    _final_report(client, cid, artifact_dir)
    return cid


def _final_report(client: BoMcpClient, cid: str, artifact_dir: Path) -> None:
    """Print a summary of all results and fetch diagnostics."""
    try:
        results = client.get_results(cid)
    except BoMcpClientError as exc:
        _tagged_print("ALERT", f"Could not fetch results: {exc}")
        return

    successes = [r for r in results if r.get("objective_values", {}).get("yield") is not None]
    yields = [r["objective_values"]["yield"] for r in successes]

    _tagged_print("EVENT", f"=== FINAL REPORT for {cid} ===")
    _tagged_print("EVENT", f"Total results: {len(results)}")
    _tagged_print("EVENT", f"Successful: {len(successes)}")
    if yields:
        _tagged_print("EVENT", f"Best yield: {max(yields):.2f}%")
        _tagged_print("EVENT", f"Mean yield: {sum(yields)/len(yields):.2f}%")
        _tagged_print("EVENT", f"Worst yield: {min(yields):.2f}%")

    # Write a summary file.
    summary = {
        "campaign_id": cid,
        "total_results": len(results),
        "successful": len(successes),
        "best_yield": max(yields) if yields else None,
        "mean_yield": sum(yields) / len(yields) if yields else None,
        "worst_yield": min(yields) if yields else None,
        "ts": _now_iso(),
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # Fetch diagnostics (expensive — do once at end).
    _tagged_print("EVENT", "Fetching diagnostics (may take a while)...")
    try:
        diag = client.get_diagnostics(cid, verbosity="standard", timeout_s=300)
        (artifact_dir / "diagnostics.json").write_text(json.dumps(diag, indent=2, default=str))
        _tagged_print("EVENT", "Diagnostics saved.")
    except BoMcpClientError as exc:
        _tagged_print("ALERT", f"Diagnostics failed: {exc}")

    # Print the campaign id line for easy extraction.
    print(f"BO_MCP_CAMPAIGN_ID={cid}", flush=True)