from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_bo.autonomous_continuation import DEFAULT_ROBOFLEX_CAMPAIGN_ID
from robochemflex_yield_bo.continuation import DEFAULT_HISTORY
from robochemflex_yield_only_bo.continuation import DEFAULT_SOURCE_CAMPAIGN_ID, run

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely resume yield-only campaign by retrying measurement #22 before continuing to 28 valid results.")
    parser.add_argument("--campaign-id", default="1970655b-a702-4963-874b-6973489cc89d")
    parser.add_argument("--source-campaign-id", default=DEFAULT_SOURCE_CAMPAIGN_ID)
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--artifact-dir", type=Path, default=None)
    parser.add_argument("--expected-seed-count", type=int, default=20)
    parser.add_argument("--expected-roboflex-campaign-id", default=DEFAULT_ROBOFLEX_CAMPAIGN_ID)
    parser.add_argument("--max-new-measurements", type=int, default=7)
    parser.add_argument("--target-total-results", type=int, default=28)
    parser.add_argument("--required-pending-suggestion-id", default="31d5114e-3796-4b21-9d5f-d7e9a31378b0")
    parser.add_argument("--retry-base-sample-name", default="bo_31d5114e-3")
    parser.add_argument("--retry-prior-attempts", type=int, default=1)
    parser.add_argument("--max-nmr-retries", type=int, default=3)
    parser.add_argument("--retry-pause-s", type=float, default=30.0)
    parser.add_argument("--bo-timeout-s", type=float, default=300.0)
    parser.add_argument("--bo-generate-timeout-s", type=float, default=1200.0)
    parser.add_argument("--run-timeout-s", type=float, default=21600.0)
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--quiet-stdout", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--resume-bo-if-paused", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pause-bo-on-exit", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true", default=True, help="Print plan only. Default.")
    parser.add_argument("--execute", dest="dry_run", action="store_false", help="Allow BO/RoboFlex writes; requires --confirm-autonomous-hardware.")
    parser.add_argument("--live-read-checks", action="store_true", help="In dry-run mode, perform read-only BO/RoboFlex preflight checks.")
    parser.add_argument("--confirm-autonomous-hardware", action="store_true", help="Required with --execute before POST /v1/runs.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
