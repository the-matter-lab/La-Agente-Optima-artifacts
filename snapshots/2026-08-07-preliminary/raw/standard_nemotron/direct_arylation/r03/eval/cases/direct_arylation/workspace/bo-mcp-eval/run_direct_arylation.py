#!/usr/bin/env python3
"""
Entry point for Direct Arylation BO-MCP campaign.

Usage:
    python run_direct_arylation.py [--campaign-id CAMPAIGN_ID] [--max-attempts N] [--poll-s N] [--heartbeat-s N] [--stop-file PATH]

Environment variables required:
    BO_MCP_API_URL      - BO-MCP REST API base URL
    BO_MCP_API_KEY      - BO-MCP API key
    DIRECT_ARYLATION_API_URL - Oracle API base URL for yield evaluations

The campaign optimizes direct arylation reaction yield over a fixed search space
of 1,728 measured reactions with a budget of exactly 60 total attempted
oracle evaluations (including failures) across all runs/resumes.

Marker: akg-eval-0c360b08e6684de0b0ed04f50bde3b2c
Nonce: 16e7e684-7bf5-4a9b-af93-fae14403be06

Attempt tracking artifact: artifacts/<campaign_id>/attempts.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure /app is on sys.path for `domains` package (contains bo_mcp client)
APP_ROOT = "/app"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from direct_arylation_campaign.campaign import run_campaign

import argparse
import os
import sys

from direct_arylation_campaign.campaign import run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Direct Arylation Yield Optimization via BO-MCP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Resume existing campaign by ID (must contain marker akg-eval-0c360b08e6684de0b0ed04f50bde3b2c)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum total oracle evaluation attempts (including failures) for the campaign lifetime",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval for BO-MCP next_action (seconds)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat logging interval (seconds)",
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to stop file; if exists, campaign pauses gracefully",
    )
    return parser.parse_args()


def check_env() -> None:
    """Verify required environment variables are set."""
    required = ["BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print(f"[ALERT] Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        print("Set them before running:", file=sys.stderr)
        for var in missing:
            print(f"  export {var}=...", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    check_env()
    args = parse_args()

    print(f"[EVENT] Starting Direct Arylation BO campaign")
    print(f"[EVENT] Total attempt budget: {args.max_attempts}")
    print(f"[EVENT] Poll interval: {args.poll_s}s, Heartbeat: {args.heartbeat_s}s")
    print(f"[EVENT] Stop file: {args.stop_file}")
    if args.campaign_id:
        print(f"[EVENT] Resuming campaign: {args.campaign_id}")

    try:
        campaign_id, all_attempts = run_campaign(
            campaign_id=args.campaign_id,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
        )
        print(f"[EVENT] Campaign {campaign_id} completed run")
        return 0
    except KeyboardInterrupt:
        print("[EVENT] Interrupted by user")
        return 130
    except Exception as e:
        print(f"[ALERT] Campaign failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())