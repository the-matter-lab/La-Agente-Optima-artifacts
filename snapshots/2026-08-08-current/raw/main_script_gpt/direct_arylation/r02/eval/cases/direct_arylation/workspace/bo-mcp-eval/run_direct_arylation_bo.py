from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app")

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_bo.campaign import DEFAULT_CAMPAIGN_NAME, run_campaign  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the direct arylation BO campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume.")
    parser.add_argument(
        "--invocation-attempt-budget",
        type=int,
        default=60,
        help="Maximum number of oracle attempts to spend in this process invocation.",
    )
    parser.add_argument("--backend", default="baybe")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--initial-design-size", type=int, default=15)
    parser.add_argument("--random-seed", type=int, default=20260730)
    parser.add_argument("--campaign-name", default=DEFAULT_CAMPAIGN_NAME)
    parser.add_argument("--oracle-timeout-s", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logfire.info(
        "starting_direct_arylation_campaign",
        campaign_id=args.campaign_id,
        invocation_attempt_budget=args.invocation_attempt_budget,
        backend=args.backend,
        batch_size=args.batch_size,
        initial_design_size=args.initial_design_size,
        random_seed=args.random_seed,
    )
    summary = run_campaign(
        campaign_id=args.campaign_id,
        invocation_attempt_budget=args.invocation_attempt_budget,
        backend=args.backend,
        batch_size=args.batch_size,
        initial_design_size=args.initial_design_size,
        random_seed=args.random_seed,
        campaign_name=args.campaign_name,
        oracle_timeout_s=args.oracle_timeout_s,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
