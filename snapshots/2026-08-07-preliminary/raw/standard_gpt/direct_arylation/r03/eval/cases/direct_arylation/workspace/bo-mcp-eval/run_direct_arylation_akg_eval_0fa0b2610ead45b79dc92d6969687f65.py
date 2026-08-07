from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_akg_eval_0fa0b2610ead45b79dc92d6969687f65.campaign import RunConfig, run_campaign
from direct_arylation_akg_eval_0fa0b2610ead45b79dc92d6969687f65.search_space import DEFAULT_ARTIFACT_DIR, TOTAL_ATTEMPT_BUDGET

configure_logfire(console=False)
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or resume the direct arylation BO-MCP campaign.")
    parser.add_argument("--campaign-id", help="Existing BO-MCP campaign id to resume.")
    parser.add_argument(
        "--artifact-dir",
        default=str(DEFAULT_ARTIFACT_DIR),
        help="Workspace-relative artifact directory for logs and summaries.",
    )
    parser.add_argument(
        "--max-new-attempts",
        type=int,
        default=TOTAL_ATTEMPT_BUDGET,
        help="Maximum new attempted evaluations to execute in this invocation.",
    )
    parser.add_argument("--poll-s", type=int, default=180, help="Polling/backoff interval in seconds.")
    parser.add_argument("--heartbeat-s", type=int, default=1800, help="Heartbeat interval in seconds.")
    parser.add_argument(
        "--stop-file",
        default="STOP",
        help="Stop-file path checked at the top of each loop iteration.",
    )
    parser.add_argument(
        "--oracle-timeout-s",
        type=float,
        default=60.0,
        help="Timeout in seconds for each oracle evaluation request.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.max_new_attempts < 1:
        raise SystemExit("--max-new-attempts must be at least 1")
    config = RunConfig(
        campaign_id=args.campaign_id,
        artifact_dir=Path(args.artifact_dir),
        max_new_attempts=args.max_new_attempts,
        total_attempt_budget=TOTAL_ATTEMPT_BUDGET,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=Path(args.stop_file),
        oracle_timeout_s=args.oracle_timeout_s,
    )
    run_campaign(config)


if __name__ == "__main__":
    main()
