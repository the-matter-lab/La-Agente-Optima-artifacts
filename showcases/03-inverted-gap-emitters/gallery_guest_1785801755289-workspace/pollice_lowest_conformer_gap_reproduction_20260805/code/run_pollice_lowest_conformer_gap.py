from __future__ import annotations

import argparse
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire(console=False)
logfire.instrument_requests()

from pollice_lowest_conformer_gap.campaign import run_campaign  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run/resume the Pollice 2021 lowest-conformer TD-DFT gap BO-MCP campaign.")
    parser.add_argument("--csv-path", default="pollice_2021_geometry_available.csv")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume/reopen.")
    parser.add_argument("--artifact-dir", default="pollice_lowest_conformer_gap_artifacts")
    parser.add_argument("--stop-file", default="STOP")
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--max-iterations", type=int, default=10, help="Per-invocation BO suggestion/evaluation loop budget.")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--initial-design-size", type=int, default=5)
    parser.add_argument("--heavy-atom-cutoff", type=int, default=56)
    parser.add_argument("--fingerprint-components", type=int, default=32)
    parser.add_argument("--random-seed", type=int, default=2021)
    parser.add_argument("--run-nonce", default=None)
    parser.add_argument("--client-timeout-s", type=float, default=120.0)
    parser.add_argument("--suggestion-timeout-s", type=float, default=900.0)
    parser.add_argument("--eval-timeout-s", type=float, default=7200.0)
    parser.add_argument("--pyscf-timeout-s", type=float, default=5400.0)
    parser.add_argument("--crest-threads", type=int, default=4)
    parser.add_argument("--limit-candidates", type=int, default=None, help="Validation/smoke-test only; omit for the full filtered library.")
    parser.add_argument("--synthetic-evaluator", action="store_true", help="Smoke-test only; bypasses CREST/PySCF and submits deterministic fake objectives.")
    parser.add_argument("--terminate-on-exit", action="store_true", help="Use only for smoke-test campaigns.")
    parser.add_argument("--pyscf-smoke-only", action="store_true", help="Run one tiny PySCF result-shape smoke test and do not touch BO-MCP.")
    parser.add_argument("--pyscf-smoke-timeout-s", type=float, default=120.0)
    return parser


if __name__ == "__main__":
    sys.exit(run_campaign(build_parser().parse_args()))
