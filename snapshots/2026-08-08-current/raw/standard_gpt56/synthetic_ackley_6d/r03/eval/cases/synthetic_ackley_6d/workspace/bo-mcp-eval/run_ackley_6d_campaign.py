#!/usr/bin/env python3
import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley_6d_campaign.campaign import run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run/resume the owned BO-MCP Ackley-6D campaign")
    parser.add_argument("--campaign-id")
    parser.add_argument("--attempt-budget", type=int, default=60)
    parser.add_argument("--poll-s", type=int, default=180)
    parser.add_argument("--heartbeat-s", type=int, default=1800)
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    args = parser.parse_args()
    if args.attempt_budget < 1:
        parser.error("--attempt-budget must be at least 1")
    if not 120 <= args.poll_s <= 300:
        parser.error("--poll-s must be between 120 and 300")
    if args.heartbeat_s < 1:
        parser.error("--heartbeat-s must be at least 1")
    return args


def main() -> None:
    args = parse_args()
    run_campaign(
        campaign_id=args.campaign_id,
        attempt_budget=args.attempt_budget,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
    )


if __name__ == "__main__":
    main()
