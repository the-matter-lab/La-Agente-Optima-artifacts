import argparse
import os
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley_6d_baybe.campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or resume the owned BO-MCP Ackley 6D BayBE campaign.")
    parser.add_argument("--campaign-id")
    parser.add_argument("--artifact-dir", default="artifacts/ackley_6d_baybe")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--invocation-attempt-limit", type=int)
    parser.add_argument("--poll-s", type=int, default=180)
    parser.add_argument("--heartbeat-s", type=int, default=1800)
    parser.add_argument("--stop-file", default="STOP")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    run_campaign(
        campaign_id=args.campaign_id,
        artifact_dir=Path(args.artifact_dir),
        batch_size=args.batch_size,
        invocation_attempt_limit=args.invocation_attempt_limit,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=Path(args.stop_file),
    )


if __name__ == "__main__":
    main()
