#!/usr/bin/env python
"""Entry point for direct arylation BO campaign.

Usage:
    python run_direct_arylation.py [--campaign-id CAMPAIGN_ID] [--poll-s POLL_S] [--heartbeat-s HEARTBEAT_S] [--stop-file STOP_FILE] [--artifact-dir ARTIFACT_DIR] [--oracle-timeout ORACLE_TIMEOUT]

Environment variables required:
    BO_MCP_API_URL: Base URL for BO-MCP API
    BO_MCP_API_KEY: [REDACTED] key for BO-MCP
    DIRECT_ARYLATION_API_URL: Base URL for direct arylation oracle
"""

import argparse
import os
import sys
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_bo.campaign import run_campaign


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run direct arylation yield optimization BO campaign"
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Existing campaign ID to resume (omit for new campaign)",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Poll interval for next_action checks (seconds, 120-300)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval for liveness logs (seconds)",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=Path("STOP"),
        help="Path to stop file; if exists, pause after current iteration",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory for per-attempt artifact files",
    )
    parser.add_argument(
        "--oracle-timeout",
        type=float,
        default=15.0,
        help="Timeout for oracle calls (seconds)",
    )

    args = parser.parse_args()

    # Validate poll interval
    if not 120 <= args.poll_s <= 300:
        print(f"[ALERT] poll-s must be between 120 and 300, got {args.poll_s}", file=sys.stderr)
        return 1

    # Configure logfire
    configure_logfire()
    logfire.instrument_requests()

    # Check required env vars
    required_env = ["BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"]
    missing = [var for var in required_env if not os.getenv(var)]
    if missing:
        print(f"[ALERT] Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    # Run campaign
    try:
        summary = run_campaign(
            campaign_id=args.campaign_id,
            artifact_dir=args.artifact_dir,
            stop_file=args.stop_file,
            poll_interval_s=args.poll_s,
            heartbeat_interval_s=args.heartbeat_s,
            oracle_timeout_s=args.oracle_timeout,
        )

        # Print final summary for parent agent
        print("\n[RESULT] === CAMPAIGN SUMMARY ===")
        print(f"[RESULT] Campaign ID: {summary['campaign_id']}")
        print(f"[RESULT] Total attempts: {summary['total_attempts']}")
        print(f"[RESULT] Successful evaluations: {summary['successful_evaluations']}")
        if summary['best_conditions']:
            print(f"[RESULT] Best yield: {summary['best_yield']:.2f}%")
            print(f"[RESULT] Best conditions: {summary['best_conditions']}")
        else:
            print("[RESULT] No successful evaluations")
        print("[RESULT] ===========================\n")

        return 0

    except KeyboardInterrupt:
        print("[EVENT] Interrupted by user", flush=True)
        return 130
    except Exception as exc:
        print(f"[ALERT] Campaign failed: {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())