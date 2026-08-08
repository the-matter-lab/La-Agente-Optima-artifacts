#!/usr/bin/env python
"""CLI entrypoint for the direct-arylation yield BO campaign (BO-MCP + BayBE)."""

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire(console=False)  # keep stdout limited to tagged campaign lines
logfire.instrument_requests()

from direct_arylation_yield.campaign import Config, run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default=None, help="resume/reopen an existing campaign")
    parser.add_argument("--total-budget", type=int, default=60, help="max attempted evaluations, campaign-wide")
    parser.add_argument("--max-attempts", type=int, default=60, help="max attempted evaluations this invocation")
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--oracle-timeout-s", type=float, default=120.0)
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()

    run(
        Config(
            campaign_id=args.campaign_id,
            total_budget=args.total_budget,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            oracle_timeout_s=args.oracle_timeout_s,
            stop_file=args.stop_file,
            artifacts_dir=args.artifacts_dir,
        )
    )


if __name__ == "__main__":
    main()
