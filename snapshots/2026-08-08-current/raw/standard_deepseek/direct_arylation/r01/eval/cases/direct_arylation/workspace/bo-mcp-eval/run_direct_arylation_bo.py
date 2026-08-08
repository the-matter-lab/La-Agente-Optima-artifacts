#!/usr/bin/env python3
"""run_direct_arylation_bo.py — BO-MCP campaign entrypoint.

Optimise measured yield of a direct arylation reaction over a fixed,
fully crossed 5-parameter search space with exactly 60 attempted
objective evaluations.

Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab

Usage:
Usage:
    PYTHONPATH=/app python3 run_direct_arylation_bo.py [--campaign-id ID] [--max-attempts N]

Environment:
    BO_MCP_API_URL            — BO-MCP REST API base URL (required)
    BO_MCP_API_KEY            — BO-MCP API key (required)
    DIRECT_ARYLATION_API_URL  — Oracle evaluator base URL (required)
"""

from __future__ import annotations

import argparse
import os
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_bo.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BO-MCP direct arylation yield optimisation"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume/reopen an existing campaign instead of creating one.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Hard budget of oracle evaluations for this invocation (default: 60).",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Seconds between next_action polls when server says wait (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between liveness heartbeats (default: 1800).",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-marker file (default: STOP).",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts",
        help="Directory for append-only provenance files (default: artifacts).",
    )
    args = parser.parse_args()

    # ── env checks ──────────────────────────────────────────────────
    missing = []
    for var in ("BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        print(f"[ALERT] Missing required env vars: {', '.join(missing)}", flush=True)
        sys.exit(1)

    logfire.info("direct_arylation_bo starting", campaign_id=args.campaign_id)

    try:
        summary = run_campaign(
            campaign_id=args.campaign_id,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
            artifact_dir=args.artifact_dir,
        )
    except Exception:
        logfire.error("direct_arylation_bo fatal error")
        raise

    logfire.info("direct_arylation_bo finished", **summary)


if __name__ == "__main__":
    main()