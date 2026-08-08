import argparse
from pathlib import Path

import logfire
from direct_arylation_baybe.campaign import run_campaign
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id")
    parser.add_argument("--artifact-dir", default="artifacts/direct_arylation_baybe")
    parser.add_argument("--attempt-budget", type=int, default=60)
    parser.add_argument("--poll-s", type=int, default=180)
    parser.add_argument("--heartbeat-s", type=int, default=1800)
    parser.add_argument("--stop-file", default="STOP")
    parser.add_argument("--oracle-timeout-s", type=float, default=120.0)
    args = parser.parse_args()
    if not 0 <= args.attempt_budget <= 60:
        parser.error("--attempt-budget must be between 0 and 60")
    if not 120 <= args.poll_s <= 300:
        parser.error("--poll-s must be between 120 and 300 seconds")
    run_campaign(
        campaign_id=args.campaign_id,
        artifact_dir=Path(args.artifact_dir),
        invocation_attempt_budget=args.attempt_budget,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=Path(args.stop_file),
        oracle_timeout_s=args.oracle_timeout_s,
    )


if __name__ == "__main__":
    main()
