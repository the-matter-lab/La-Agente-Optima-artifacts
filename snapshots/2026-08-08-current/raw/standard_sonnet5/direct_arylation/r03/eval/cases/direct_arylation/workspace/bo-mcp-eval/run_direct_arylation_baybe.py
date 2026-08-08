#!/usr/bin/env python3
"""CLI entrypoint for the direct-arylation-yield BO-MCP campaign (BayBE backend).

Benchmark ownership marker (present in every BO-MCP campaign created here):
    akg-eval-9209d1682dba47dfb5f5735d25356061
Cache-buster nonce (preserved verbatim): 4b764ac7-d36a-4203-89a4-800a2274f65c

Required environment variables:
    BO_MCP_API_URL             BO-MCP API base URL
    BO_MCP_API_KEY             BO-MCP API key
    DIRECT_ARYLATION_API_URL   Oracle base URL (POST {url}/v1/evaluate)

Usage:
    uv run python run_direct_arylation_baybe.py [--campaign-id ID] [--budget 60]

On resume after a pause/kill, re-run with --campaign-id <the printed id>.
"""
import argparse
import logging
import os
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_baybe.campaign import run

DEFAULT_ARTIFACT_DIR = "direct_arylation_baybe_artifacts"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign-id", default=None, help="Resume an existing BO-MCP campaign.")
    p.add_argument("--budget", type=int, default=60,
                    help="Total attempted oracle evaluations for this benchmark (default: 60; do not exceed).")
    p.add_argument("--batch-size", type=int, default=1, help="Suggestions requested per BO round.")
    p.add_argument("--initial-design-size", type=int, default=10,
                    help="Space-filling warmup points before BayBE switches to model-driven acquisition.")
    p.add_argument("--poll-s", type=int, default=180,
                    help="Seconds bounding a single suggestion-generation call (keep within 120-300).")
    p.add_argument("--heartbeat-s", type=int, default=1800, help="Seconds between [HEARTBEAT] liveness lines.")
    p.add_argument("--stop-file", default="STOP", help="Presence of this file requests a graceful pause.")
    p.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR, help="Directory for provenance artifacts.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    configure_logfire()
    logfire.instrument_requests()

    if not (120 <= args.poll_s <= 300):
        print(f"[ALERT] --poll-s={args.poll_s} outside recommended [120,300]; continuing anyway.", flush=True)

    for env_var in ("BO_MCP_API_URL", "BO_MCP_API_KEY", "DIRECT_ARYLATION_API_URL"):
        if not os.environ.get(env_var):
            print(f"[ALERT] required environment variable {env_var} is not set", flush=True)
            return 2

    os.makedirs(args.artifact_dir, exist_ok=True)
    log_path = os.path.join(args.artifact_dir, "run.log")
    logging.basicConfig(filename=log_path, level=logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    artifact_path = os.path.join(args.artifact_dir, "results.jsonl")
    summary_path = os.path.join(args.artifact_dir, "summary.json")

    logfire.info("starting direct_arylation_baybe campaign run",
                  campaign_id=args.campaign_id, budget=args.budget)

    campaign_id, summary = run(
        campaign_id=args.campaign_id,
        budget=args.budget,
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
