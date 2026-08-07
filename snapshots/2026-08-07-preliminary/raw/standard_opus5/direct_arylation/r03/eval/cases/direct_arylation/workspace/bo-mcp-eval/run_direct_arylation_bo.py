#!/usr/bin/env python
"""CLI entrypoint: run/resume the direct arylation yield BO-MCP campaign (BayBE backend).

Campaign name marker: akg-eval-1c094af49d534fef9861377f221f0f69
"""

from __future__ import annotations

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_bo.campaign import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default=None, help="Resume an existing BO-MCP campaign.")
    parser.add_argument("--max-attempts", type=int, default=60, help="Oracle attempts this invocation.")
    parser.add_argument("--max-successes", type=int, default=60, help="Server-side result cap.")
    parser.add_argument("--batch-size", type=int, default=1, help="Suggestions per BO iteration.")
    parser.add_argument("--initial-design-size", type=int, default=8)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--poll-s", type=float, default=180.0, help="Retry wait on empty generation.")
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--stop-file", default="STOP")
    parser.add_argument("--oracle-timeout-s", type=float, default=120.0)
    parser.add_argument("--request-timeout-s", type=float, default=300.0)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
