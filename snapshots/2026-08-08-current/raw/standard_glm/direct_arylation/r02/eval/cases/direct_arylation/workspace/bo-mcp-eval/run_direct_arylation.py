#!/usr/bin/env python3
"""Entrypoint for the direct arylation BO campaign.

Usage
-----
  # Fresh run (creates a new campaign):
  uv run python run_direct_arylation.py

  # Resume an existing campaign:
  uv run python run_direct_arylation.py --campaign-id <ID>

  # Custom budget and artifact directory:
  uv run python run_direct_arylation.py --max-attempts 60 --artifact-dir ./artifacts

Environment variables (required):
  BO_MCP_API_URL          — BO-MCP REST API base URL
  BO_MCP_API_KEY          — BO-MCP API key
  DIRECT_ARYLATION_API_URL — Oracle base URL

Cache-buster nonce: a375b9bd-ae19-499a-9006-4ecc7a3bc68d
"""

from __future__ import annotations

import argparse
import os
import sys

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from direct_arylation_campaign.campaign import run_campaign
from direct_arylation_campaign.search_space import MARKER


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Direct arylation BO campaign (60-attempt budget)"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Existing campaign ID to resume (omit to create a new campaign)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum attempted objective evaluations (default: 60)",
    )
    parser.add_argument(
        "--artifact-dir",
        default="./artifacts",
        help="Directory for evaluation log and diagnostics (default: ./artifacts)",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="File whose existence triggers a graceful pause (default: STOP)",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=5.0,
        help="Seconds to sleep between iterations (default: 5.0)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800.0,
        help="Seconds between [HEARTBEAT] lines (default: 1800)",
    )
    args = parser.parse_args()

    # Validate required environment variables early
    missing = []
    if not os.getenv("BO_MCP_API_URL"):
        missing.append("BO_MCP_API_URL")
    if not os.getenv("BO_MCP_API_KEY"):
        missing.append("BO_MCP_API_KEY")
    if not os.getenv("DIRECT_ARYLATION_API_URL"):
        missing.append("DIRECT_ARYLATION_API_URL")
    if missing:
        print(f"[ALERT] Missing environment variables: {', '.join(missing)}", flush=True)
        sys.exit(1)

    # Build the BO-MCP client
    client = BoMcpClient.from_env()

    # Ensure artifact directory exists
    os.makedirs(args.artifact_dir, exist_ok=True)

    print(f"[EVENT] Campaign marker: {MARKER}", flush=True)
    print(f"[EVENT] Budget: {args.max_attempts} attempted evaluations", flush=True)
    print(f"[EVENT] Artifact dir: {args.artifact_dir}", flush=True)

    campaign_id = run_campaign(
        client=client,
        campaign_id=args.campaign_id,
        max_attempts=args.max_attempts,
        artifact_dir=args.artifact_dir,
        stop_file=args.stop_file,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )

    print(f"[EVENT] Campaign ID: {campaign_id}", flush=True)


if __name__ == "__main__":
    main()
