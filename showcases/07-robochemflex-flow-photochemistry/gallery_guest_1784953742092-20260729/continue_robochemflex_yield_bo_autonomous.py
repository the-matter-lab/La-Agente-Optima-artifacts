from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.autonomous_continuation import (
    DEFAULT_BO_CAMPAIGN_ID,
    DEFAULT_HISTORY,
    DEFAULT_PREVIEW_DIR,
    DEFAULT_PREVIEW_SUGGESTION_ID,
    DEFAULT_RECREATED_DIR,
    DEFAULT_ROBOFLEX_CAMPAIGN_ID,
    run,
)

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomously continue the recreated RoboChemFlex BO campaign from reviewed measurement #10.")
    parser.add_argument("--campaign-id", default=DEFAULT_BO_CAMPAIGN_ID)
    parser.add_argument("--recreated-artifact-dir", type=Path, default=DEFAULT_RECREATED_DIR)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--measurement10-suggestion-id", default=DEFAULT_PREVIEW_SUGGESTION_ID)
    parser.add_argument("--expected-roboflex-campaign-id", default=DEFAULT_ROBOFLEX_CAMPAIGN_ID)
    parser.add_argument("--expected-initial-results", type=int, default=9)
    parser.add_argument("--target-total-results", type=int, default=20)
    parser.add_argument("--max-new-experiments", type=int, default=11)
    parser.add_argument("--bo-timeout-s", type=float, default=240.0)
    parser.add_argument("--run-timeout-s", type=float, default=21600.0)
    parser.add_argument("--poll-s", type=float, default=180.0, help="RoboFlex polling interval in seconds; production default 180s and allowed range is 120-300s.")
    parser.add_argument("--heartbeat-s", type=float, default=1800.0, help="Low-frequency stdout heartbeat interval in seconds; production default 1800s and allowed range is 1800-3600s.")
    parser.add_argument("--zero-no-peak-streak-limit", type=int, default=5, help="Stop after this many consecutive completed experiments with zero yield and/or no NMR peak evidence.")
    parser.add_argument("--quiet-stdout", action=argparse.BooleanOptionalAction, default=True, help="Print only meaningful state changes, alerts, heartbeats, and completed-experiment analyses.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print the static plan without BO/RoboFlex writes. This is the default.")
    parser.add_argument("--execute", dest="dry_run", action="store_false", help="Leave dry-run mode. Still requires --confirm-autonomous-hardware.")
    parser.add_argument("--live-read-checks", action="store_true", help="In dry-run mode only, also perform live read-only BO/RoboFlex checks.")
    parser.add_argument("--confirm-autonomous-hardware", action="store_true", help="Required with --execute before any RoboFlex hardware submission.")
    parser.add_argument("--pause-bo-on-exit", action="store_true", default=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
