#!/usr/bin/env python
"""CLI entrypoint for the direct arylation reaction-yield BO-MCP campaign.

nonce: 63564e1a-5ca5-4172-97e2-374479e19e77
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from direct_arylation_yield import campaign  # noqa: E402

DEFAULT_LOG = Path("direct_arylation_yield_run.log")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default=None, help="Resume/continue an existing campaign.")
    parser.add_argument("--max-attempts", type=int, default=60, help="Attempted evaluations this invocation.")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--initial-design-size", type=int, default=6)
    parser.add_argument("--random-seed", type=int, default=2805)
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--eval-timeout-s", type=float, default=120.0)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()

    logging.basicConfig(
        filename=str(args.log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logfire.info("direct arylation campaign invocation", max_attempts=args.max_attempts)

    campaign.run(
        campaign_id=args.campaign_id,
        max_attempts=args.max_attempts,
        batch_size=args.batch_size,
        initial_design_size=args.initial_design_size,
        random_seed=args.random_seed,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        artifacts_root=args.artifacts_root,
        eval_timeout_s=args.eval_timeout_s,
    )


if __name__ == "__main__":
    main()
