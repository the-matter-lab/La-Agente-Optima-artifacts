from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from ackley_baybe_bomcp.campaign import CampaignConfig, run_campaign

configure_logfire()
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the BO-MCP Ackley 6D synthetic benchmark campaign with the BayBE backend.",
    )
    parser.add_argument("--campaign-id", default=None, help="Resume or reopen an existing campaign.")
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="BO-MCP suggestion-generation timeout in seconds.",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between liveness heartbeats on stdout.",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=Path("STOP"),
        help="When this file exists at loop start, the run pauses cleanly and exits.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Validate BO-MCP wiring and intake without creating a campaign or consuming evaluations.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = CampaignConfig(
        campaign_id=args.campaign_id,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        smoke_test=args.smoke_test,
    )
    return run_campaign(config)


if __name__ == "__main__":
    raise SystemExit(main())
