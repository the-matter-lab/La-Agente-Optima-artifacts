#!/usr/bin/env python3
"""Entrypoint for the 6D Ackley BO-MCP campaign.

Usage:
    python run_ackley6d.py [--campaign-id ID] [--stop-file PATH] [--poll-s S] [--heartbeat-s S]

Environment:
    BO_MCP_API_URL   — BO-MCP server base URL (required)
    BO_MCP_API_KEY   — API key for authenticated endpoints (required)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Logfire instrumentation ────────────────────────────────────────────
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

# ── Local imports ──────────────────────────────────────────────────────
from ackley6d.campaign import NONCE, MARKER, CAMPAIGN_NAME, TOTAL_BUDGET, run_campaign

WORKSPACE = Path(__file__).resolve().parent
ARTIFACT_DIR = WORKSPACE / "artifacts"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"6D Ackley BO-MCP campaign  marker={MARKER}"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume an existing campaign by ID. Omit to create a new one.",
    )
    parser.add_argument(
        "--stop-file",
        default=str(WORKSPACE / "STOP"),
        help="Path to stop-file; campaign pauses when this file exists (default: ./STOP).",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180,
        help="Timeout in seconds for suggestion generation (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800,
        help="Seconds between heartbeat log lines (default: 1800).",
    )
    args = parser.parse_args()

    logfire.info(
        "ackley6d campaign starting",
        nonce=NONCE,
        marker=MARKER,
        campaign_name=CAMPAIGN_NAME,
        budget=TOTAL_BUDGET,
        campaign_id=args.campaign_id,
    )

    stop_file = Path(args.stop_file) if args.stop_file else None

    cid = run_campaign(
        campaign_id=args.campaign_id,
        artifact_dir=ARTIFACT_DIR,
        stop_file=stop_file,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )

    logfire.info("ackley6d campaign finished", campaign_id=cid)
    print(f"[EVENT] Campaign ID: {cid}", flush=True)
    print(f"[EVENT] Artifacts: {ARTIFACT_DIR}", flush=True)


if __name__ == "__main__":
    main()
