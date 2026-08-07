#!/usr/bin/env python
"""Run the direct arylation BO-MCP benchmark campaign.

Cache-buster nonce: f8cfd946-3972-4d92-97e3-98d984cbbd2a
"""

from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_yield_bo.campaign import RunConfig, run_campaign
from direct_arylation_yield_bo.search_space import (
    CACHE_BUSTER_NONCE,
    CAMPAIGN_SLUG,
    DEFAULT_CAMPAIGN_MAX_OBSERVATIONS,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RANDOM_SEED,
)

configure_logfire()
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Direct arylation BO-MCP benchmark runner "
            f"(cache-buster nonce {CACHE_BUSTER_NONCE})."
        )
    )
    parser.add_argument("--campaign-id", help="Existing BO-MCP campaign id to resume/reopen.")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts") / CAMPAIGN_SLUG,
        help="Artifact root directory. Campaign-specific outputs are written under <artifact-root>/<campaign-id>/.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help="Maximum total attempted oracle evaluations allowed for this campaign ledger.",
    )
    parser.add_argument(
        "--campaign-max-observations",
        type=int,
        default=DEFAULT_CAMPAIGN_MAX_OBSERVATIONS,
        help="BO-MCP campaign observation budget used only when creating a fresh campaign.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Campaign random seed passed into BO-MCP campaign creation.",
    )
    parser.add_argument(
        "--initial-design-size",
        type=int,
        default=DEFAULT_INITIAL_DESIGN_SIZE,
        help="Warm-start design size before model-driven BO suggestions.",
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180.0,
        help="Seconds to sleep between completed attempts while the loop remains active.",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=float,
        default=1800.0,
        help="Seconds between [HEARTBEAT] liveness messages.",
    )
    parser.add_argument(
        "--request-timeout-s",
        type=float,
        default=60.0,
        help="HTTP timeout for each oracle evaluation POST request.",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        default=Path("STOP"),
        help="If this file exists at the top of a loop iteration, the runner prints [EVENT], deletes it, pauses, and exits cleanly.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = RunConfig(
        campaign_id=args.campaign_id,
        artifact_root=args.artifact_root,
        max_attempts=args.max_attempts,
        campaign_max_observations=args.campaign_max_observations,
        random_seed=args.random_seed,
        initial_design_size=args.initial_design_size,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        request_timeout_s=args.request_timeout_s,
        stop_file=args.stop_file,
    )
    return run_campaign(config)


if __name__ == "__main__":
    raise SystemExit(main())
