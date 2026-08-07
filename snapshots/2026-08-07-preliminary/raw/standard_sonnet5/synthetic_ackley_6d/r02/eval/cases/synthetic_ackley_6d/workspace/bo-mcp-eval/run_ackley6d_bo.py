#!/usr/bin/env python3
"""CLI entrypoint for the synthetic Ackley-6D BO-MCP campaign.

Usage:
    uv run python run_ackley6d_bo.py [--campaign-id ID] [options]

See HOW_TO_EXECUTE_CAMPAIGN.md for full usage, tags, and resume instructions.
Context nonce (preserve exactly): 1bc98eae-1366-4f95-ba15-243c959b907b
"""

import argparse
from pathlib import Path

import logfire

from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley6d_bo.campaign import run
from ackley6d_bo.intake import DEFAULT_BATCH_SIZE, DEFAULT_INITIAL_DESIGN_SIZE


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic Ackley-6D BO-MCP campaign")
    parser.add_argument("--campaign-id", default=None, help="Resume an existing campaign instead of creating one.")
    parser.add_argument("--seed", type=int, default=42, help="Campaign-level random seed (new campaigns only).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Suggestions requested per generate call (new campaigns only).")
    parser.add_argument("--initial-design-size", type=int, default=DEFAULT_INITIAL_DESIGN_SIZE, help="Space-filling warmup size (new campaigns only).")
    parser.add_argument("--poll-s", type=float, default=180.0, help="Timeout budget for each generate_suggestions call (120-300s recommended).")
    parser.add_argument("--heartbeat-s", type=float, default=1800.0, help="Seconds between [HEARTBEAT] liveness lines.")
    parser.add_argument("--stop-file", default="STOP", help="Path checked at the top of each loop iteration; delete-on-honor.")
    parser.add_argument("--artifact-dir", default="ackley6d_bo_artifacts", help="Directory for the append-only results.csv/results.jsonl artifacts.")
    args = parser.parse_args()

    logfire.info("ackley6d_bo campaign invocation starting", campaign_id=args.campaign_id)

    run(
        campaign_id=args.campaign_id,
        seed=args.seed,
        batch_size=args.batch_size,
        initial_design_size=args.initial_design_size,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=Path(args.stop_file),
        artifact_dir=Path(args.artifact_dir),
    )


if __name__ == "__main__":
    main()
