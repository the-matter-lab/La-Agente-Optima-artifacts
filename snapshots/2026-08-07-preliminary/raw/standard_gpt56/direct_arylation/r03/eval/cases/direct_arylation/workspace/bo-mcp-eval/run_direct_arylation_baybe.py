#!/usr/bin/env python3
import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from direct_arylation_baybe.campaign import run_campaign  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the direct arylation BayBE campaign")
    parser.add_argument("--campaign-id")
    parser.add_argument("--invocation-attempts", type=int, default=60)
    parser.add_argument("--artifact-dir", type=Path, default=Path("direct_arylation_artifacts"))
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    parser.add_argument("--poll-s", type=float, default=180.0)
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--oracle-timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    campaign_id = run_campaign(
        campaign_id=args.campaign_id,
        invocation_attempts=args.invocation_attempts,
        artifact_dir=args.artifact_dir,
        stop_file=args.stop_file,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        oracle_timeout_s=args.oracle_timeout_s,
    )
    print(f"[EVENT] normal shutdown campaign_id={campaign_id}", flush=True)


if __name__ == "__main__":
    main()
