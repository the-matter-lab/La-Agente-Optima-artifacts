from __future__ import annotations

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.recreate_history import run

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recreate the RoboChemFlex BO-MCP campaign and import historical R0044-R0052 results only."
    )
    parser.add_argument("--campaign-id", help="Existing newly-created BO-MCP campaign id to seed after an interrupted run.")
    parser.add_argument("--campaign-name", help="Name for the recreated BO-MCP campaign; defaults to a UTC-stamped name.")
    parser.add_argument("--run-nonce", help="Unique nonce for fresh campaign creation idempotency.")
    parser.add_argument("--history-csv", default="campaign_logs/roboflex_experiment_log_latest.csv")
    parser.add_argument("--artifact-dir", help="Artifact directory for recreation audit files.")
    parser.add_argument("--bo-timeout-s", type=float, default=180.0)
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate local history files only; do not contact BO-MCP.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
