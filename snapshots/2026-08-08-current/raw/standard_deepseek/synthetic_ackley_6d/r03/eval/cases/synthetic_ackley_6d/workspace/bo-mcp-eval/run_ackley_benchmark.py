#!/usr/bin/env python3
"""CLI entrypoint for the 6D Ackley BO-MCP benchmark campaign.

Usage::

    uv run python run_ackley_benchmark.py [--campaign-id ID] [--max-evals N]

Environment: ``BO_MCP_API_URL``, ``BO_MCP_API_KEY`` required.
"""

import argparse
import os
import sys
import time

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley_benchmark.campaign import run
from ackley_benchmark.reporter import emit_alert, emit_event


def main() -> None:
    parser = argparse.ArgumentParser(description="6D Ackley BO-MCP benchmark")
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume/reopen an existing campaign instead of creating a new one.",
    )
    parser.add_argument(
        "--max-evals",
        type=int,
        default=60,
        help="Hard cap on attempted evaluations for this invocation (default: 60).",
    )
    parser.add_argument(
        "--artifact-dir",
        default="ackley_artifacts",
        help="Directory for append-only JSONL artifact (default: ackley_artifacts).",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Seconds between next_action polls when server says wait (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Seconds between liveness heartbeats (default: 1800).",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-marker file (default: STOP).",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Optional path for a run log (tagged lines also go to stdout).",
    )
    args = parser.parse_args()

    if args.log_path:
        os.environ["LOG_PATH"] = args.log_path

    emit_event(f"starting ackley benchmark max_evals={args.max_evals}")

    client = BoMcpClient.from_env()
    emit_event("BO-MCP client initialised")

    campaign_id = run(
        client=client,
        campaign_id=args.campaign_id,
        max_evaluations=args.max_evals,
        artifact_dir=args.artifact_dir,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
    )

    emit_event(f"campaign_id={campaign_id} — done")
    print(f"\nBO_MCP_CAMPAIGN_ID={campaign_id}")


if __name__ == "__main__":
    main()