#!/usr/bin/env python
from __future__ import annotations

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

from hood_co_bisphosphine_bo.campaign import run


def parse_args():
    parser = argparse.ArgumentParser(description="Finite-library BO-MCP/PySCF campaign for cationic Co(II) bisphosphine complexes.")
    parser.add_argument("--campaign-id", default=None, help="Resume an existing BO-MCP campaign id.")
    parser.add_argument("--campaign-name", default="hood-co-bisphosphine-cationic-coii")
    parser.add_argument("--artifacts-dir", default="hood_co_bisphosphine_artifacts")
    parser.add_argument("--library-only", action="store_true", help="Report the full candidate library and exit before BO/calculations.")
    parser.add_argument("--create-only", action="store_true", help="Validate/create the BO-MCP campaign after library reporting, then exit before suggestions/calculations.")
    parser.add_argument("--run-calculations", action="store_true", help="Allow Estructural + PySCF evaluations. Without this or --mock-evaluator, the script is library-only.")
    parser.add_argument("--mock-evaluator", action="store_true", help="Use a deterministic no-calculation evaluator for smoke testing only.")
    parser.add_argument("--max-successes", type=int, default=1, help="Per-invocation budget of completed BO suggestions/evaluations.")
    parser.add_argument("--hood-warm-start-bo10", action="store_true", help="Preset: run exactly four documented chemically diverse warm-start candidates, then run 10 BO-selected iterations.")
    parser.add_argument("--bo-iterations", type=int, default=None, help="Override BO-selected iteration count after warm starts; intended for bounded smoke tests.")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--stop-file", default="STOP")
    parser.add_argument("--bo-timeout-s", type=float, default=120.0)
    parser.add_argument("--suggestion-timeout-s", type=float, default=900.0)
    parser.add_argument("--preflight-timeout-s", type=float, default=3.0, help="Socket timeout for production Estructural connectivity preflight.")
    parser.add_argument("--random-seed", type=int, default=2020)
    parser.add_argument("--charge", type=int, default=1, help="Assumed complex charge for [Co(acac)(P2)]+.")
    parser.add_argument("--spin-multiplicity", type=int, default=2, help="Assumed low-spin Co(II) doublet; override if needed.")
    parser.add_argument("--basis-set", default="def2-svp")
    parser.add_argument("--xc-functional", default="pbe")
    parser.add_argument("--geometry-max-steps", type=int, default=200)
    parser.add_argument("--workflow-timeout-s", type=float, default=7200.0)
    parser.add_argument("--terminate-on-exit", action="store_true", help="Terminate campaign at end; intended for bounded smoke tests only.")
    return parser.parse_args()


def main() -> None:
    configure_logfire(console=False)
    logfire.instrument_requests()
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
