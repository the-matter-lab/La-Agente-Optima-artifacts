from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.continuation import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_CAMPAIGN_ID,
    DEFAULT_HISTORY,
    DEFAULT_ROBRIDGE_CAMPAIGN,
    run,
)

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or submit RoboChemFlex measurement #10 from the recreated BO-MCP campaign.")
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID, help="Recreated BO-MCP campaign id.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY, help="Historical RoboFlex result log used for request equivalence checks.")
    parser.add_argument("--expected-completed-results", type=int, default=9)
    parser.add_argument("--expected-robridge-campaign", default=DEFAULT_ROBRIDGE_CAMPAIGN)
    parser.add_argument("--bo-timeout-s", type=float, default=180.0)
    parser.add_argument("--submit", action="store_true", help="Submit an already reviewed preview request to RoboFlex.")
    parser.add_argument("--confirm-reviewed", action="store_true", help="Required with --submit after a human reviews preview artifacts.")
    parser.add_argument("--force-resubmit", action="store_true", help="Override duplicate artifact/RoboFlex sample-name guards.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
