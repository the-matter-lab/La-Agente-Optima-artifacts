#!/usr/bin/env python
"""Entrypoint for the 6-D Ackley BO-MCP campaign (baybe backend).

Usage:
    # Fresh run
    uv run python run_akg_ackley_6d.py

    # Resume an existing campaign
    uv run python run_akg_ackley_6d.py --campaign-id <ID>

    # Custom budget / stop file
    uv run python run_akg_ackley_6d.py --max-evals 60 --stop-file STOP
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from akg_ackley_6d.campaign import (
    TOTAL_BUDGET,
    build_intake,
    run_loop,
)
from akg_ackley_6d.reporting import ResultsArtifact


def _tagged(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def _load_prior_results(client: BoMcpClient, campaign_id: str, artifact: ResultsArtifact) -> int:
    """Populate artifact with results already on the server; return count."""
    from akg_ackley_6d.evaluator import evaluate as _eval

    try:
        rows = client.get_results(campaign_id)
    except Exception as exc:
        _tagged("ALERT", f"Could not fetch prior results: {exc}")
        return 0

    for i, row in enumerate(rows, start=1):
        pvals = row.get("parameter_values", {})
        ovals = row.get("objective_values", {})
        # Recompute raw_response from parameter values (deterministic)
        raw_resp = None
        try:
            coords = {k: float(pvals[k]) for k in ("x_1","x_2","x_3","x_4","x_5","x_6")}
            raw_resp = _eval(**coords)["raw_response"]
        except Exception:
            pass
        artifact.append(
            evaluation_index=i,
            parameter_values=pvals,
            objective_values=ovals,
            status="success",
            raw_response=raw_resp,
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="6-D Ackley BO-MCP campaign")
    parser.add_argument("--campaign-id", default=None, help="Existing campaign ID to resume")
    parser.add_argument("--max-evals", type=int, default=TOTAL_BUDGET, help="Total evaluation budget (across all invocations)")
    parser.add_argument("--poll-s", type=float, default=180.0, help="Poll interval (s)")
    parser.add_argument("--heartbeat-s", type=float, default=1800.0, help="Heartbeat interval (s)")
    parser.add_argument("--stop-file", default="STOP", help="Path to stop-file")
    args = parser.parse_args()

    # ── artifact directory ──────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = Path("artifacts") / f"ackley_6d_{ts}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    results_path = artifact_dir / "results.jsonl"
    artifact = ResultsArtifact(results_path)

    # ── BO-MCP client ──────────────────────────────────────────────
    client = BoMcpClient.from_env()

    # ── campaign creation or resume ─────────────────────────────────
    campaign_id = args.campaign_id
    prior_evals = 0

    if campaign_id is None:
        intake = build_intake()
        _tagged("EVENT", "Validating campaign intake …")
        try:
            validation = client.validate_intake(intake)
            if not validation.get("valid", False):
                _tagged("ALERT", f"Intake validation failed: {validation}")
                sys.exit(1)
        except Exception as exc:
            _tagged("ALERT", f"Intake validation error: {exc}")
            sys.exit(1)

        _tagged("EVENT", "Creating campaign …")
        idem_key = BoMcpClient.make_idempotency_key("create", intake["name"])
        try:
            create_resp = client.create_campaign(intake, idempotency_key=idem_key)
        except Exception as exc:
            _tagged("ALERT", f"Campaign creation failed: {exc}")
            sys.exit(1)

        if not create_resp.get("success", False):
            _tagged("ALERT", f"Campaign creation rejected: {create_resp.get('errors', [])}")
            sys.exit(1)

        campaign_id = create_resp["campaign_id"]
        _tagged("EVENT", f"Campaign created: {campaign_id}")
    else:
        _tagged("EVENT", f"Resuming campaign: {campaign_id}")
        # Load prior results into artifact and count them
        prior_evals = _load_prior_results(client, campaign_id, artifact)
        _tagged("EVENT", f"Prior evaluations on server: {prior_evals}")

        # Ensure campaign is running
        try:
            info = client.get_campaign(campaign_id)
            status = info.get("status", "")
            if status == "paused":
                client.lifecycle(campaign_id, action="resume")
                _tagged("EVENT", "Campaign resumed from paused")
            elif status == "completed":
                client.lifecycle(campaign_id, action="reopen")
                _tagged("EVENT", "Campaign reopened from completed")
        except Exception as exc:
            _tagged("ALERT", f"Could not check/resume campaign: {exc}")

    # ── save campaign id for resume ─────────────────────────────────
    (artifact_dir / "campaign_id.txt").write_text(campaign_id + "\n")

    # ── compute remaining budget ────────────────────────────────────
    remaining = max(0, args.max_evals - prior_evals)
    if remaining == 0:
        _tagged("EVENT", f"Budget already exhausted ({prior_evals}/{args.max_evals})")
        artifact.finalize()
        best = artifact.best()
        if best:
            _tagged("RESULT",
                     f"BEST surface_response={best['objective_values'].get('surface_response', 'N/A')} "
                     f"raw_response={best.get('raw_response', 'N/A')} "
                     + " ".join(f"{k}={v}" for k, v in best["parameter_values"].items()))
        return

    # ── run the loop ────────────────────────────────────────────────
    _tagged("EVENT", f"Starting loop: remaining={remaining}/{args.max_evals} campaign={campaign_id}")
    try:
        run_loop(
            campaign_id=campaign_id,
            client=client,
            artifact=artifact,
            max_evals=args.max_evals,  # total budget; run_loop uses artifact.n_attempted()
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
        )
    except KeyboardInterrupt:
        _tagged("EVENT", "Interrupted by user; pausing campaign")
        try:
            client.lifecycle(campaign_id, action="pause")
        except Exception:
            pass

    # ── pause campaign at end of invocation ─────────────────────────
    try:
        info = client.get_campaign(campaign_id)
        if info.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            _tagged("EVENT", "Campaign paused at end of invocation")
    except Exception:
        pass

    _tagged("EVENT", f"Artifact: {results_path}")
    _tagged("EVENT", f"Resume with: uv run python run_akg_ackley_6d.py --campaign-id {campaign_id}")


if __name__ == "__main__":
    main()
