#!/usr/bin/env python
"""CLI entrypoint: Ackley-6D synthetic surface BO campaign via BO-MCP (BayBE)."""

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire(console=False)  # keep stdout limited to the tagged campaign lines

logfire.instrument_requests()

from ackley6d.campaign import Config, run  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign-id", default=None, help="Resume/continue an existing campaign.")
    p.add_argument("--max-attempts", type=int, default=60, help="Attempted evaluations budget.")
    p.add_argument("--init-size", type=int, default=12, help="Initial space-filling batch size.")
    p.add_argument("--batch-size", type=int, default=4, help="Model-driven batch size.")
    p.add_argument("--seed", type=int, default=913477)
    p.add_argument("--acquisition", default="expected_improvement")
    p.add_argument("--poll-s", type=float, default=180.0)
    p.add_argument("--heartbeat-s", type=float, default=1800.0)
    p.add_argument("--stop-file", type=Path, default=Path("STOP"))
    p.add_argument("--artifacts-root", type=Path, default=Path("artifacts"))
    a = p.parse_args()

    run(
        Config(
            campaign_id=a.campaign_id,
            max_attempts=a.max_attempts,
            init_size=a.init_size,
            batch_size=a.batch_size,
            seed=a.seed,
            acquisition=a.acquisition,
            poll_s=a.poll_s,
            heartbeat_s=a.heartbeat_s,
            stop_file=a.stop_file,
            artifacts_root=a.artifacts_root,
        )
    )


if __name__ == "__main__":
    main()
