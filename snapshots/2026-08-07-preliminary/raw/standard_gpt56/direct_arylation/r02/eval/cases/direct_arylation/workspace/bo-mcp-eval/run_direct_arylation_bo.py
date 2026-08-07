#!/usr/bin/env python3
"""CLI entrypoint for the BO-MCP direct arylation campaign."""

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_bo.campaign import run_campaign  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", help="Resume this owned BO-MCP campaign")
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    parser.add_argument("--oracle-timeout-s", type=float, default=120.0)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run exactly one attempt; use only with a non-live test oracle",
    )
    args = parser.parse_args()
    if not 120 <= args.poll_s <= 300:
        parser.error("--poll-s must be between 120 and 300 seconds")
    if args.heartbeat_s <= 0 or args.oracle_timeout_s <= 0:
        parser.error("timeouts must be positive")
    return args


def main() -> None:
    args = parse_args()
    run_campaign(
        campaign_id=args.campaign_id,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        oracle_timeout_s=args.oracle_timeout_s,
        smoke_test=args.smoke_test,
    )


if __name__ == "__main__":
    main()
