#!/usr/bin/env python3
"""CLI entrypoint for the direct arylation BO-MCP campaign.

Usage:
    python run_direct_arylation_bo.py [--campaign-id ID] [--stop-file PATH] [--poll-s S] [--heartbeat-s S]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_bo.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BO-MCP campaign for direct arylation yield optimization"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Existing campaign ID to resume (omit to create a new campaign)",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-file; campaign pauses when this file exists (default: STOP)",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180,
        help="Seconds between loop iterations (default: 180)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800,
        help="Seconds between heartbeat log lines (default: 1800)",
    )
    args = parser.parse_args()

    # Artifacts directory
    artifacts_dir = Path("artifacts")
    stop_file = Path(args.stop_file)

    # Validate required env vars
    missing = []
    if not os.getenv("BO_MCP_API_URL"):
        missing.append("BO_MCP_API_URL")
    if not os.getenv("BO_MCP_API_KEY"):
        missing.append("BO_MCP_API_KEY")
    if not os.getenv("DIRECT_ARYLATION_API_URL"):
        missing.append("DIRECT_ARYLATION_API_URL")
    if missing:
        print(f"[ALERT] Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    campaign_id = run_campaign(
        campaign_id=args.campaign_id,
        artifacts_dir=artifacts_dir,
        stop_file=stop_file,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )

    print(f"\nCampaign complete. ID: {campaign_id}")
    print(f"Artifacts: {artifacts_dir.resolve()}")


if __name__ == "__main__":
    main()
