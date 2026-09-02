from __future__ import annotations

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.campaign import run

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run/resume the RoboChemFlex BO-MCP campaign.")
    parser.add_argument("--campaign-id", help="Existing BO-MCP campaign id to resume.")
    parser.add_argument("--campaign-name", default="robochemflex_yield_baybe")
    parser.add_argument("--run-nonce", help="Unique nonce for fresh BO campaign creation idempotency.")
    parser.add_argument("--mode", choices=["local-simulation", "robridge-real"], default="local-simulation")
    parser.add_argument("--allow-real-roboflex", action="store_true", help="Required with --mode robridge-real.")
    parser.add_argument("--allow-hardware-retry", action="store_true", help="Permit an intentional repeat after a failed RoboFlex run.")
    parser.add_argument("--retry-suffix", help="Suffix added to sample names for intentional repeats, e.g. r2.")
    parser.add_argument("--max-successes", type=int, default=20, help="Per-invocation successful evaluations budget.")
    parser.add_argument("--skip-informed-seeds", action="store_true", help="For smoke tests only: go directly to BO suggestions.")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--terminate-bo-on-exit", action="store_true", help="Use for smoke campaigns only.")
    parser.add_argument("--pause-bo-on-exit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--bo-timeout-s", type=float, default=180.0)
    parser.add_argument("--run-timeout-s", type=float, default=7200.0)
    parser.add_argument("--experiment-type", default="Flow Photochemical Reaction")
    parser.add_argument("--analytical-method", default="NMR")
    parser.add_argument("--robridge-campaign-name", default="robochemflex_yield_bo")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
