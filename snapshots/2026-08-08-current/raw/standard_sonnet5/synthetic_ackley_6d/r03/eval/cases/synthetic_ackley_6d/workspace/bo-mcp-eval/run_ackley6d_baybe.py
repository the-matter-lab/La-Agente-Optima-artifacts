#!/usr/bin/env python3
"""CLI entrypoint: Ackley-6D BayBE BO-MCP synthetic benchmark campaign.

Cache-buster nonce: 20c0e1a3-857c-440c-9206-992c37c2f31f

Synthetic benchmark only -- calls BO-MCP exclusively, no PySCF/CREST/MOF/
RAISE/RoboFlex or any other chemistry/experimental evaluator.
"""
import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley6d_baybe.campaign import create_or_resume, run


def main() -> None:
    parser = argparse.ArgumentParser(description="Ackley-6D BayBE BO-MCP campaign")
    parser.add_argument(
        "--campaign-id", default=None, help="Resume/continue an existing campaign id"
    )
    parser.add_argument(
        "--poll-s",
        type=float,
        default=180.0,
        help=(
            "Accepted for monitoring-contract parity (120-300s). This campaign's "
            "loop is synchronous (pure-math evaluation, no external async job), "
            "so there is no idle wait to throttle; the value is logged only."
        ),
    )
    parser.add_argument("--heartbeat-s", type=float, default=1800.0)
    parser.add_argument("--stop-file", default="STOP")
    args = parser.parse_args()

    client = BoMcpClient.from_env()
    campaign_id = create_or_resume(client, args.campaign_id)
    artifact_dir = f"artifacts/{campaign_id}"

    logfire.info(
        "ackley6d_baybe campaign start",
        campaign_id=campaign_id,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )
    print(f"[EVENT] poll_s={args.poll_s} heartbeat_s={args.heartbeat_s} stop_file={args.stop_file}", flush=True)

    run(client, campaign_id, artifact_dir, args.stop_file, args.heartbeat_s)


if __name__ == "__main__":
    main()
