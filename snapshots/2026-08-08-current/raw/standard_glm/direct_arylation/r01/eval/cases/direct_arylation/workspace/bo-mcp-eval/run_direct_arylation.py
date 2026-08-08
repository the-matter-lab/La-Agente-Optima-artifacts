#!/usr/bin/env python3
"""CLI entrypoint for the direct-arylation BO-MCP campaign.

Usage:
    python run_direct_arylation.py [--campaign-id ID] [--budget 60] [--stop-file STOP]

Environment variables (required):
    BO_MCP_API_URL       — BO-MCP REST API base URL
    BO_MCP_API_KEY       — BO-MCP API key
    DIRECT_ARYLATION_API_URL — Oracle base URL

Environment variables (optional):
    ARTIFACT_DIR         — Directory for artifacts (default: ./artifacts)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure /app is on sys.path so domains.* and grafico.* are importable
_APP_DIR = "/app"
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

import argparse
import os
import sys
from pathlib import Path

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from direct_arylation_bo.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Direct-arylation BO-MCP campaign runner"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Existing campaign ID to resume (omit to create new)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=60,
        help="Maximum attempted evaluations for this invocation (default: 60)",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval in seconds (default: 180)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds (default: 1800)",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop file (default: STOP in cwd)",
    )
    args = parser.parse_args()

    # Validate required environment
    missing = []
    if not os.getenv("BO_MCP_API_URL"):
        missing.append("BO_MCP_API_URL")
    if not os.getenv("BO_MCP_API_KEY"):
        missing.append("BO_MCP_API_KEY")
    if not os.getenv("DIRECT_ARYLATION_API_URL"):
        missing.append("DIRECT_ARYLATION_API_URL")
    if missing:
        print(f"[ALERT] Missing required env vars: {', '.join(missing)}", flush=True)
        sys.exit(1)

    client = BoMcpClient.from_env()
    artifact_dir = Path(os.getenv("ARTIFACT_DIR", "./artifacts"))

    campaign_id = run_campaign(
        client=client,
        campaign_id=args.campaign_id,
        budget=args.budget,
        artifact_dir=artifact_dir,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=Path(args.stop_file) if args.stop_file else None,
    )

    # Final line for automated extraction
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)


if __name__ == "__main__":
    main()
