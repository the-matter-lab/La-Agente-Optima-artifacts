from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.campaign import RunConfig, run_campaign
from ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.search_space import CAMPAIGN_MARKER, TOTAL_BUDGET

configure_logfire(console=False)
logfire.instrument_requests()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ackley 6D BO-MCP benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Resume or reopen an existing campaign id.")
    parser.add_argument(
        "--campaign-label",
        default="main",
        help="Label suffix for newly created campaign names. Ignored when --campaign-id is provided.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=f"artifacts_{CAMPAIGN_MARKER}",
        help="Artifact directory written under the current working directory.",
    )
    parser.add_argument(
        "--total-budget",
        type=int,
        default=TOTAL_BUDGET,
        help="Total benchmark budget. Keep the default 60 for the requested benchmark.",
    )
    parser.add_argument(
        "--max-attempts-this-run",
        type=int,
        default=None,
        help="Optional per-invocation attempt cap for smoke tests or partial runs.",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling/timeout base in seconds (recommended 120-300).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds.",
    )
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Path to a stop marker checked at the top of each loop iteration.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=271828,
        help="Campaign RNG seed used when creating a new campaign.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_campaign(
        RunConfig(
            artifact_root=Path(args.artifact_dir),
            stop_file=Path(args.stop_file),
            campaign_id=args.campaign_id,
            campaign_label=args.campaign_label,
            total_budget=args.total_budget,
            max_attempts_this_run=args.max_attempts_this_run,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            random_seed=args.random_seed,
        )
    )


if __name__ == "__main__":
    main()
