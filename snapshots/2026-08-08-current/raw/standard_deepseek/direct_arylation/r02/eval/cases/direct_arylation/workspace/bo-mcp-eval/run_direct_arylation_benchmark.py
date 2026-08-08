#!/usr/bin/env python3
"""Entrypoint for the direct-arylation reaction-yield BO-MCP campaign.

Usage:
  PYTHONPATH=/app python run_direct_arylation_benchmark.py [--campaign-id ID] [--max-attempts N]

Environment:
  BO_MCP_API_URL            — BO-MCP REST API base URL (required)
  BO_MCP_API_KEY            — BO-MCP API key (required)
  DIRECT_ARYLATION_API_URL  — Yield oracle base URL (required)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from direct_arylation_benchmark.intake import build_intake, CAMPAIGN_MARKER
from direct_arylation_benchmark.evaluator import evaluate as oracle_evaluate
from direct_arylation_benchmark.objective import ResultLedger
from direct_arylation_benchmark.campaign import run_campaign


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Direct-arylation yield BO-MCP campaign"
    )
    p.add_argument(
        "--campaign-id",
        default=None,
        help="Existing campaign ID to resume (omit to create a new one).",
    )
    p.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Hard cap on oracle evaluations for this invocation (default: 60).",
    )
    p.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Seconds between iterations (default: 180).",
    )
    p.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between heartbeat lines (default: 1800).",
    )
    p.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-marker file (default: STOP in CWD).",
    )
    p.add_argument(
        "--results-jsonl",
        default=None,
        help="Path for results JSONL (default: results.jsonl).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    # ── validate env ─────────────────────────────────────────────────
    missing = []
    for var in ("BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        print(f"[ALERT] Missing required env vars: {', '.join(missing)}", flush=True)
        sys.exit(1)

    # ── client ───────────────────────────────────────────────────────
    client = BoMcpClient.from_env()

    # ── campaign name ────────────────────────────────────────────────
    campaign_name = f"direct-arylation-yield-{CAMPAIGN_MARKER}"

    # ── intake ───────────────────────────────────────────────────────
    intake = build_intake(campaign_name=campaign_name)

    # ── results ledger ───────────────────────────────────────────────
    ledger = ResultLedger()

    results_jsonl = args.results_jsonl or "results.jsonl"

    def on_result(result: dict) -> None:
        ledger.record(
            candidate=result["candidate"],
            status=result["status"],
            yield_value=result["yield"],
            suggestion_id=result["suggestion_id"],
            iteration=result["iteration"],
        )
        # Append to JSONL after every result for crash safety.
        ledger.write_jsonl(results_jsonl)

    # ── run ──────────────────────────────────────────────────────────
    campaign_id = run_campaign(
        client=client,
        intake=intake,
        campaign_id=args.campaign_id,
        evaluate_fn=oracle_evaluate,
        on_result=on_result,
        max_attempts=args.max_attempts,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
    )

    # ── final report ─────────────────────────────────────────────────
    print(f"[EVENT] Campaign ID: {campaign_id}", flush=True)
    ledger.print_final_report()

    # ── write campaign manifest ──────────────────────────────────────
    manifest = {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "results_jsonl": results_jsonl,
        "package_modules": [
            "direct_arylation_benchmark/__init__.py",
            "direct_arylation_benchmark/search_space.py",
            "direct_arylation_benchmark/intake.py",
            "direct_arylation_benchmark/evaluator.py",
            "direct_arylation_benchmark/objective.py",
            "direct_arylation_benchmark/campaign.py",
        ],
        "run_entrypoint": "run_direct_arylation_benchmark.py",
        "latest_artifact_dir": str(Path.cwd()),
    }
    with open("campaign_manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[EVENT] Wrote campaign_manifest.json", flush=True)


if __name__ == "__main__":
    main()