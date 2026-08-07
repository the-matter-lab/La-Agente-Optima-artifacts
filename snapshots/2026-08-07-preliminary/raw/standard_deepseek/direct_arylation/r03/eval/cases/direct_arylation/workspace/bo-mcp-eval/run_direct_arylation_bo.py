#!/usr/bin/env python3
"""CLI entrypoint for the direct-arylation yield-optimisation BO-MCP campaign.

Usage::

    uv run python run_direct_arylation_bo.py [--campaign-id CID] [--max-attempts 60]

Environment variables
---------------------
BO_MCP_API_URL            : required — BO-MCP REST API base URL
BO_MCP_API_KEY            : [REDACTED] — BO-MCP API key
DIRECT_ARYLATION_API_URL  : required — oracle base URL
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from domains.bo_mcp.client import BoMcpClient

from direct_arylation_bo.campaign import run_campaign

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Direct-arylation yield-optimisation BO-MCP campaign"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume an existing campaign instead of creating a new one.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum attempted evaluations this invocation (default: 60).",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Seconds between BO iterations (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between heartbeat lines (default: 1800).",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-file; delete it to request graceful shutdown (default: STOP).",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts_direct_arylation",
        help="Directory for logs, results, diagnostics (default: artifacts_direct_arylation).",
    )
    args = parser.parse_args()

    # ── validate env ──────────────────────────────────────────────────
    missing = []
    for var in ("BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        print(f"[ALERT] Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    artifact_dir = Path(args.artifact_dir)

    client = BoMcpClient.from_env(timeout_s=120.0)

    cid = run_campaign(
        client,
        campaign_id=args.campaign_id,
        artifact_dir=artifact_dir,
        max_attempts=args.max_attempts,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
    )

    # Final line for easy extraction.
    print(f"BO_MCP_CAMPAIGN_ID={cid}", flush=True)


if __name__ == "__main__":
    main()