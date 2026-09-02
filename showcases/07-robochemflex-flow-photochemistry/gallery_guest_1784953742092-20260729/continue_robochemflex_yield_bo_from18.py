from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.autonomous_continuation import DEFAULT_RECREATED_DIR, DEFAULT_ROBOFLEX_CAMPAIGN_ID
from robochemflex_yield_bo.continuation import DEFAULT_HISTORY
from robochemflex_yield_bo.current_resume import DEFAULT_BO_CAMPAIGN_ID, DEFAULT_FAILED17_SUGGESTION_ID, run

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely resume RoboChemFlex BO from 18 completed BO results to 20.")
    parser.add_argument("--campaign-id", default=DEFAULT_BO_CAMPAIGN_ID)
    parser.add_argument("--recreated-artifact-dir", type=Path, default=DEFAULT_RECREATED_DIR)
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--expected-roboflex-campaign-id", default=DEFAULT_ROBOFLEX_CAMPAIGN_ID)
    parser.add_argument("--expected-current-results", type=int, default=18)
    parser.add_argument("--target-total-results", type=int, default=20)
    parser.add_argument("--max-new-measurements", type=int, default=2)
    parser.add_argument("--blocked-suggestion-ids", default=DEFAULT_FAILED17_SUGGESTION_ID)
    parser.add_argument("--bo-timeout-s", type=float, default=300.0)
    parser.add_argument("--bo-generate-timeout-s", type=float, default=1200.0, help="Per-attempt timeout for BO suggestion generation.")
    parser.add_argument("--bo-generate-retries", type=int, default=2, help="Retry count after the first generation attempt.")
    parser.add_argument("--bo-generate-recovery-wait-s", type=float, default=120.0, help="Wait between post-timeout BO recovery polls/retries.")
    parser.add_argument("--bo-generate-recovery-polls", type=int, default=3, help="Post-timeout recovery polls before retrying or stopping.")
    parser.add_argument("--run-timeout-s", type=float, default=21600.0)
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--zero-no-peak-streak-limit", type=int, default=5)
    parser.add_argument("--initial-zero-no-peak-streak", type=int, default=0)
    parser.add_argument("--quiet-stdout", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--resume-bo-if-paused", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pause-bo-on-exit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print the plan without BO/RoboFlex writes. This is the default.")
    parser.add_argument("--execute", dest="dry_run", action="store_false", help="Leave dry-run mode. Still requires --confirm-autonomous-hardware.")
    parser.add_argument("--live-read-checks", action="store_true", help="In dry-run mode only, perform live read-only BO/RoboFlex checks.")
    parser.add_argument("--confirm-autonomous-hardware", action="store_true", help="Required with --execute before any RoboFlex hardware submission.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
