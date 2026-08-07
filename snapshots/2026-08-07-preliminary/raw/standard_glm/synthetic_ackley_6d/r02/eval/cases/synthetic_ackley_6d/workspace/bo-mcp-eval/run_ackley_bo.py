#!/usr/bin/env python3
"""CLI entrypoint for the Ackley 6-D BO-MCP campaign.

Usage:
    uv run python run_ackley_bo.py [--campaign-id ID] [--artifact-dir DIR] \
                                    [--stop-file PATH] [--poll-s S] [--heartbeat-s S]

Environment:
    BO_MCP_API_URL   — BO-MCP REST API base URL (required)
    BO_MCP_API_KEY   — BO-MCP API key (required)
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure /app is on sys.path so domains.bo_mcp.client is importable
# when running with plain python3 (uv run has a read-only-egg-info build issue).
_APP_DIR = os.environ.get("APP_DIR", "/app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import argparse
import os
import sys

# Logfire instrumentation (best-effort; not fatal if unavailable).
try:
    import logfire
    from grafico.core.logfire_config import configure_logfire

    configure_logfire()
    logfire.instrument_requests()
except Exception:
    pass

from ackley_bo.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ackley 6-D synthetic benchmark BO-MCP campaign"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Existing campaign ID to resume (omit to create a new campaign).",
    )
    parser.add_argument(
        "--artifact-dir",
        default=os.environ.get("ARTIFACT_DIR", "."),
        help="Directory for result artifacts (default: $ARTIFACT_DIR or cwd).",
    )
    parser.add_argument(
        "--stop-file",
        default=os.environ.get("STOP_FILE", "STOP"),
        help="Path to stop-file (default: $STOP_FILE or 'STOP').",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180.0,
        help="Polling interval in seconds (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800.0,
        help="Heartbeat interval in seconds (default: 1800).",
    )
    args = parser.parse_args()

    cid = run_campaign(
        campaign_id=args.campaign_id,
        artifact_dir=args.artifact_dir,
        stop_file=args.stop_file,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )

    # Required output line for the parent agent.
    print(f"BO_MCP_CAMPAIGN_ID={cid}", flush=True)


if __name__ == "__main__":
    main()
