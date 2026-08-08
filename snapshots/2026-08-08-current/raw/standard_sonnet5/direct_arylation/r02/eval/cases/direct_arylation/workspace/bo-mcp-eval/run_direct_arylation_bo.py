#!/usr/bin/env python3
"""CLI entrypoint for the direct-arylation yield BO-MCP campaign.

See HOW_TO_EXECUTE_CAMPAIGN.md for usage, monitoring tags, and resume
instructions.
"""
from __future__ import annotations

import argparse
import os
import sys

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient  # noqa: E402

from direct_arylation_bo import campaign  # noqa: E402

DEFAULT_CACHE_BUSTER = "18bbb6cb-b2dd-48e7-8f26-5d5f6ac9b778"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign-id", default=None, help="Resume/continue this campaign instead of creating a new one.")
    p.add_argument("--max-attempts", type=int, default=60, help="Per-invocation cap on attempted objective evaluations.")
    p.add_argument("--poll-s", type=float, default=180.0, help="Backoff interval (s) when re-polling for a pending suggestion after a generation timeout. Keep within 120-300.")
    p.add_argument("--heartbeat-s", type=float, default=1800.0, help="Liveness heartbeat interval (s).")
    p.add_argument("--stop-file", default="STOP", help="If this file exists at the top of a loop iteration, pause and exit.")
    p.add_argument("--oracle-url", default=os.getenv("DIRECT_ARYLATION_API_URL"), help="Base URL for the direct-arylation oracle (env DIRECT_ARYLATION_API_URL).")
    p.add_argument("--cache-buster", default=os.getenv("DIRECT_ARYLATION_CACHE_BUSTER", DEFAULT_CACHE_BUSTER), help="Cache-buster nonce sent with every oracle request.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.oracle_url:
        print("[ALERT] DIRECT_ARYLATION_API_URL is not set and --oracle-url was not given", flush=True)
        return 2

    client = BoMcpClient.from_env()
    campaign_id = campaign.get_or_create_campaign(client, args.campaign_id, args.cache_buster)

    try:
        campaign.run(
            client=client,
            campaign_id=campaign_id,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
            oracle_url=args.oracle_url,
            cache_buster=args.cache_buster,
        )
    finally:
        campaign.finalize(client, campaign_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
