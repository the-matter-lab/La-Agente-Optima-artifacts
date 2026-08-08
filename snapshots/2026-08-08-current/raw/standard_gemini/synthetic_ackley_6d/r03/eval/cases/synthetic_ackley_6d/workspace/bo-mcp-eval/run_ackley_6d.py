#!/usr/bin/env python
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

import argparse
import sys

sys.path.insert(0, "/app")

from ackley_6d.campaign import run_campaign


def main():
    parser = argparse.ArgumentParser(
        description="Run Ackley 6D synthetic BO-MCP campaign."
    )
    parser.add_argument("--campaign-id", type=str, default=None)
    parser.add_argument(
        "--name",
        type=str,
        default="Ackley 6D Optimization",
        help="Base campaign name; ownership marker is appended automatically on create.",
    )
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--init-size", type=int, default=12)
    parser.add_argument(
        "--backend", type=str, default="botorch", choices=["auto", "botorch", "baybe"]
    )
    parser.add_argument("--poll-s", type=int, default=0)
    parser.add_argument("--heartbeat-s", type=int, default=30)
    parser.add_argument("--stop-file", type=str, default="STOP")
    parser.add_argument("--artifact-dir", type=str, default="artifacts")
    parser.add_argument("--max-evaluations", type=int, default=None)
    args = parser.parse_args()

    run_campaign(
        campaign_id=args.campaign_id,
        campaign_name=args.name,
        random_seed=args.seed,
        initial_design_size=args.init_size,
        backend=args.backend,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        artifact_dir=args.artifact_dir,
        max_evaluations=args.max_evaluations,
    )


if __name__ == "__main__":
    main()
