#!/usr/bin/env python3
"""Run the Ackley 6-D benchmark campaign via BO-MCP / BayBE.

Usage:
  uv run python run_ackley_benchmark.py [--campaign-id ID] [--stop-file STOP]
"""

import argparse
import os
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley_benchmark.orchestrator import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Ackley 6-D BO-MCP benchmark")
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume an existing campaign instead of creating one.",
    )
    parser.add_argument(
        "--max-attempted",
        type=int,
        default=60,
        help="Maximum attempted evaluations (CLI budget).",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Seconds to sleep when polling for suggestions.",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between heartbeat lines.",
    )
    parser.add_argument(
        "--stop-file",
        default=os.environ.get("STOP_FILE", "STOP"),
        help="Path to a stop marker file.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts",
        help="Directory for result artifacts.",
    )
    parser.add_argument(
        "--log-path",
        default="campaign.log",
        help="Path for the run log.",
    )
    args = parser.parse_args()

    # Unbuffered stdout for monitor-friendly tagged lines
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    run_campaign(
        max_attempted=args.max_attempted,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        campaign_id=args.campaign_id,
        artifact_dir=args.artifact_dir,
        log_path=args.log_path,
    )


if __name__ == "__main__":
    main()