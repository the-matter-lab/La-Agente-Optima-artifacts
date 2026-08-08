#!/usr/bin/env python3
"""CLI entrypoint for the Ackley-6D BayBE benchmark campaign.

Usage::

    uv run python run_ackley_benchmark.py [--campaign-id ID] [--max-evals N] ...

Environment
-----------
``BO_MCP_API_URL`` and ``BO_MCP_API_KEY`` are required.
"""

from __future__ import annotations

import argparse
import os
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley_benchmark.campaign import run_campaign
from ackley_benchmark.campaign_intake import build_intake
from ackley_benchmark.evaluator import evaluate
from ackley_benchmark.objective_extraction import (
    extract_objective_values,
    extract_raw_response,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ackley-6D BayBE benchmark")
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Resume an existing campaign instead of creating one.",
    )
    parser.add_argument(
        "--max-evals",
        type=int,
        default=60,
        help="Maximum attempted evaluations this invocation (default: 60).",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180.0,
        help="Seconds between loop iterations (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800.0,
        help="Seconds between heartbeat lines (default: 1800).",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop-file checked each iteration (default: STOP).",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts",
        help="Directory for result log, diagnostics, and summary (default: artifacts).",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Campaign RNG seed (default: 42).",
    )
    parser.add_argument(
        "--initial-design-size",
        type=int,
        default=12,
        help="Sobol warm-up points (default: 12).",
    )
    args = parser.parse_args()

    client = BoMcpClient.from_env(timeout_s=300.0)

    intake = build_intake(
        random_seed=args.random_seed,
        initial_design_size=args.initial_design_size,
        batch_size=1,
    )

    campaign_id = run_campaign(
        client=client,
        intake=intake,
        evaluate=evaluate,
        extract_objective_values=extract_objective_values,
        extract_raw_response=extract_raw_response,
        max_evaluations=args.max_evals,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        campaign_id=args.campaign_id,
        artifact_dir=args.artifact_dir,
    )

    # Final line for easy extraction
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()