#!/usr/bin/env python3
"""CLI entrypoint for the direct-arylation-yield BO-MCP campaign.

Benchmark ownership marker (present in every campaign created here):
    akg-eval-87b85822029643db89946580a5362018
Cache-buster nonce (preserved verbatim): 2a734689-189a-4fcd-9345-42f6d8dad2f8

Required environment variables:
    BO_MCP_API_URL             BO-MCP API base URL
    BO_MCP_API_KEY             BO-MCP API key
    DIRECT_ARYLATION_API_URL   Oracle base URL (POST {url}/v1/evaluate)

Usage:
    uv run python run_direct_arylation_yield.py [--campaign-id ID] [--max-attempts 60]

On resume after a pause/kill, re-run with --campaign-id <the printed id>.
"""
import argparse
import logging
import os
import sys

import logfire

from grafico.core.logfire_config import configure_logfire

from direct_arylation_yield.campaign import run

DEFAULT_ARTIFACT_DIR = "direct_arylation_yield_artifacts"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign-id", default=None, help="Resume an existing BO-MCP campaign.")
    p.add_argument("--max-attempts", type=int, default=60,
                    help="CLI budget of oracle attempts for this invocation (default: 60).")
    p.add_argument("--batch-size", type=int, default=5, help="Suggestions requested per BO round.")
    p.add_argument("--initial-design-size", type=int, default=10,
                    help="Space-filling warmup points before BayBE switches to model-driven acquisition.")
    p.add_argument("--poll-s", type=int, default=180, help="Seconds between polls after a slow/timed-out generate call (120-300).")
    p.add_argument("--heartbeat-s", type=int, default=1800, help="Seconds between [HEARTBEAT] liveness lines.")
    p.add_argument("--stop-file", default="STOP", help="Presence of this file requests a graceful pause.")
    p.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR, help="Directory for provenance artifacts.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    configure_logfire(console=False)
    logfire.instrument_requests()

    os.makedirs(args.artifact_dir, exist_ok=True)
    log_path = os.path.join(args.artifact_dir, "run.log")
    logging.basicConfig(filename=log_path, level=logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    for env_var in ("BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"):
        if not os.environ.get(env_var):
            print(f"[ALERT] required environment variable {env_var} is not set", flush=True)
            return 2

    artifact_path = os.path.join(args.artifact_dir, "results.jsonl")
    summary_path = os.path.join(args.artifact_dir, "summary.json")

    logfire.info("starting direct_arylation_yield campaign run", campaign_id=args.campaign_id,
                  max_attempts=args.max_attempts)

    campaign_id = run(
        campaign_id=args.campaign_id,
        max_attempts=args.max_attempts,
        batch_size=args.batch_size,
        initial_design_size=args.initial_design_size,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        artifact_path=artifact_path,
        summary_path=summary_path,
    )

    return 0 if campaign_id else 1


if __name__ == "__main__":
    sys.exit(main())
