#!/usr/bin/env python3
"""CLI entrypoint for the Ackley 6D BO-MCP benchmark campaign.

Usage:
    uv run python run_ackley6d.py [--campaign-id CAMPAIGN_ID]
        [--artifact-dir artifacts] [--poll-s 180] [--heartbeat-s 1800]
        [--stop-file STOP]

Environment: requires BO_MCP_API_URL and BO_MCP_API_KEY.
"""
import argparse

import logfire

from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley6d_bo.campaign import run  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ackley 6D BO-MCP campaign runner")
    p.add_argument("--campaign-id", default=None, help="Resume an existing campaign")
    p.add_argument("--artifact-dir", default="artifacts", help="Directory for the result artifact")
    p.add_argument("--poll-s", type=int, default=180, help="Backoff seconds on transient errors (120-300)")
    p.add_argument("--heartbeat-s", type=int, default=1800, help="Heartbeat interval in seconds")
    p.add_argument("--stop-file", default="STOP", help="Sentinel file checked at the top of each loop iteration")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logfire.info(
        "ackley6d_campaign_start",
        campaign_id=args.campaign_id,
        artifact_dir=args.artifact_dir,
    )
    campaign_id = run(
        campaign_id=args.campaign_id,
        artifact_dir=args.artifact_dir,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
    )
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}")


if __name__ == "__main__":
    main()
