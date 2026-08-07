#!/usr/bin/env python
"""Entrypoint for 6D Ackley BO-MCP campaign.

This script runs a Bayesian optimization campaign on the 6D Ackley function
using the BO-MCP service. The campaign uses a deterministic local objective
function (no PySCF, CREST, MOF, or chemistry evaluators).

Campaign ownership marker (MUST appear in every campaign name):
    akg-eval-aadeb62aa2334f789ebf84ff0f1e2a45

Cache-buster nonce:
    87fe1294-416b-4ab4-8491-0d8cb2c43c23

Usage:
    python run_ackley_6d.py [--campaign-id CAMPAIGN_ID] [--poll-s POLL_S] [--heartbeat-s HEARTBEAT_S] [--stop-file STOP_FILE] [--artifact-dir ARTIFACT_DIR]

Environment variables required:
    BO_MCP_API_URL - Base URL for BO-MCP API (e.g., http://api:8000)
    BO_MCP_API_KEY - API key for authentication

The script is resumable: pass --campaign-id to resume an existing campaign.
A STOP file (default: STOP in current directory) can be created to gracefully pause the campaign.
"""

import argparse
import os
import sys
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

# Configure logfire
configure_logfire()
logfire.instrument_requests()

# Add the current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ackley_6d_campaign.campaign.orchestrator import run_campaign


def main():
    parser = argparse.ArgumentParser(
        description="Run 6D Ackley BO-MCP optimization campaign",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Existing campaign ID to resume (omit to create new)",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180.0,
        help="Polling interval in seconds between iterations",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800.0,
        help="Heartbeat logging interval in seconds",
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to stop file (created to pause campaign)",
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default="artifacts",
        help="Directory for results artifacts",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running campaign",
    )

    args = parser.parse_args()

    # Validate environment
    if not os.environ.get("BO_MCP_API_URL"):
        print("[ALERT] BO_MCP_API_URL environment variable not set")
        sys.exit(1)
    if not os.environ.get("BO_MCP_API_KEY"):
        print("[ALERT] BO_MCP_API_KEY environment variable not set")
        sys.exit(1)

    print("[EVENT] Starting 6D Ackley BO-MCP campaign")
    print(f"  BO_MCP_API_URL: {os.environ.get('BO_MCP_API_URL')}")
    print(f"  Campaign ID: {args.campaign_id or '(new)'}")
    print(f"  Poll interval: {args.poll_s}s")
    print(f"  Heartbeat interval: {args.heartbeat_s}s")
    print(f"  Stop file: {args.stop_file}")
    print(f"  Artifact dir: {args.artifact_dir}")
    print(f"  Marker: akg-eval-aadeb62aa2334f789ebf84ff0f1e2a45")
    print(f"  Cache-buster: 87fe1294-416b-4ab4-8491-0d8cb2c43c23")

    if args.dry_run:
        print("[EVENT] Dry run complete - configuration valid")
        return 0

    try:
        campaign_id = run_campaign(
            campaign_id=args.campaign_id,
            artifact_dir=args.artifact_dir,
            poll_interval=args.poll_s,
            heartbeat_interval=args.heartbeat_s,
            stop_file=args.stop_file,
        )
        print(f"\n[EVENT] Campaign completed: {campaign_id}")
        return 0
    except Exception as e:
        logfire.exception("Campaign failed")
        print(f"[ALERT] Campaign failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())