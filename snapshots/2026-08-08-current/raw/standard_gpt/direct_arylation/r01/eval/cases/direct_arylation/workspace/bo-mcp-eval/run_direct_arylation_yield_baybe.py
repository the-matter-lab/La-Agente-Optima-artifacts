#!/usr/bin/env python
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_yield_baybe import RunConfig, run_campaign

configure_logfire()
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the direct arylation BO-MCP campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing owned BO-MCP campaign ID to resume or reopen.")
    parser.add_argument("--max-attempts", type=int, default=60, help="Attempted objective evaluations budget for this invocation.")
    parser.add_argument("--poll-s", type=int, default=180, help="Polling cadence hint for operators and monitors.")
    parser.add_argument("--heartbeat-s", type=int, default=1800, help="Seconds between [HEARTBEAT] lines.")
    parser.add_argument("--stop-file", default="STOP", help="When this file exists at loop start, the run pauses cleanly.")
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts/direct_arylation_yield_baybe",
        help="Directory for attempts, summary, diagnostics, and run metadata.",
    )
    parser.add_argument("--oracle-timeout-s", type=float, default=60.0, help="Timeout for each oracle POST /v1/evaluate call.")
    parser.add_argument(
        "--diagnostics-timeout-s",
        type=float,
        default=600.0,
        help="Timeout for final BO-MCP diagnostics collection.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate local wiring and write artifacts without BO or oracle calls.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifacts_dir / "run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    run_campaign(
        RunConfig(
            campaign_id=args.campaign_id,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
            artifacts_dir=str(artifacts_dir),
            oracle_timeout_s=args.oracle_timeout_s,
            diagnostics_timeout_s=args.diagnostics_timeout_s,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
