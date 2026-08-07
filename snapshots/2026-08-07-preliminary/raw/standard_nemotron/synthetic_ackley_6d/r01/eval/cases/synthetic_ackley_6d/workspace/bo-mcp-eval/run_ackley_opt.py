#!/usr/bin/env python
"""Entrypoint for Ackley 6D BO-MCP optimization campaign.

Usage:
    python run_ackley_opt.py [--campaign-id CAMPAIGN_ID] [options]

Environment:
    BO_MCP_API_URL    - BO-MCP REST API base URL (required)
    BO_MCP_API_KEY    - BO-MCP API key (required)
    GRAPHCHAT_AGENT_WS_URL / VITE_WS_URL - WebSocket URL (for logfire context)
    GRAPHCHAT_ROOM    - Room identifier (default: "room")
    SPARQL_ENDPOINT   - SPARQL endpoint (default: "http://blazegraph:8080/blazegraph/namespace/kb/sparql")

Output:
    - Artifacts in ./artifacts/ (results.jsonl, results.csv, server_export.csv)
    - Campaign ID printed as: BO_MCP_CAMPAIGN_ID=<id>
    - Console tagged lines: [EVENT], [ALERT], [RESULT], [HEARTBEAT]
    - Stop file: ./STOP (create to request graceful pause)
"""

import argparse
import os
import sys
from pathlib import Path

# Configure logfire early
import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley_opt.campaign import run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ackley 6D synthetic benchmark optimization via BO-MCP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--campaign-id",
        help="Resume existing campaign by ID (must contain ownership marker)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="RNG seed for reproducible initialization",
    )
    parser.add_argument(
        "--initial-design-size",
        type=int,
        default=10,
        help="Number of Sobol initial design points",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Number of suggestions per generation call",
    )
    parser.add_argument(
        "--max-observations",
        type=int,
        default=60,
        help="Total evaluation budget (attempted evaluations)",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "botorch", "baybe"],
        default="auto",
        help="BO backend to use",
    )
    parser.add_argument(
        "--acquisition-method",
        default="auto",
        help="Acquisition function (e.g., noisy_ei, upper_confidence_bound, auto)",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts",
        help="Directory for output artifacts",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Poll interval in seconds (kept for compatibility)",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat log interval in seconds",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to stop file; create to request graceful pause",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Validate required env vars
    for var in ("BO_MCP_API_URL", "BO_MCP_API_KEY"):
        if not os.getenv(var):
            print(f"[ALERT] Required environment variable {var} not set", flush=True)
            return 1

    print("[EVENT] Starting Ackley 6D BO-MCP campaign", flush=True)
    print(f"[EVENT] BO_MCP_API_URL={os.getenv('BO_MCP_API_URL')}", flush=True)

    try:
        campaign_id, summary = run_campaign(
            campaign_id=args.campaign_id,
            random_seed=args.random_seed,
            initial_design_size=args.initial_design_size,
            batch_size=args.batch_size,
            max_observations=args.max_observations,
            backend=args.backend,
            acquisition_method=args.acquisition_method,
            artifact_dir=args.artifact_dir,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
        )

        # Emit campaign ID for downstream consumption
        print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
        return 0

    except Exception as e:
        print(f"[ALERT] Campaign failed: {e}", flush=True)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())