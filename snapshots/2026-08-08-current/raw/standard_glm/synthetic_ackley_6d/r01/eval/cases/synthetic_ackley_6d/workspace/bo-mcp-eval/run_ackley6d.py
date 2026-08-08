#!/usr/bin/env python3
"""CLI entrypoint for the 6D Ackley BO-MCP campaign.

Usage:
    PYTHONPATH=/app python3 run_ackley6d.py [--campaign-id ID] [--max-evals N] [--seed S] \
                                              [--poll-s S] [--heartbeat-s S] [--stop-file PATH]

Resume a paused/completed campaign by passing its --campaign-id.
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure /app is on sys.path for domains/grafico imports
_APP_DIR = os.environ.get("APP_DIR", "/app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

# Logfire instrumentation
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley6d.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="6D Ackley BO-MCP campaign")
    parser.add_argument("--campaign-id", default=None, help="Existing campaign ID to resume")
    parser.add_argument("--max-evals", type=int, default=60, help="Max attempted evaluations (default 60)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for campaign creation (default 42)")
    parser.add_argument("--poll-s", type=float, default=180, help="Poll interval in seconds (default 180)")
    parser.add_argument("--heartbeat-s", type=float, default=1800, help="Heartbeat interval (default 1800)")
    parser.add_argument("--stop-file", default="STOP", help="Path to stop-file marker (default STOP)")
    parser.add_argument("--artifact-dir", default="artifacts", help="Artifact output directory")
    args = parser.parse_args()

    client = BoMcpClient.from_env()

    cid = run_campaign(
        client=client,
        campaign_id=args.campaign_id,
        max_evaluations=args.max_evals,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        artifact_dir=args.artifact_dir,
        random_seed=args.seed,
    )
    print(f"BO_MCP_CAMPAIGN_ID={cid}", flush=True)


if __name__ == "__main__":
    main()
