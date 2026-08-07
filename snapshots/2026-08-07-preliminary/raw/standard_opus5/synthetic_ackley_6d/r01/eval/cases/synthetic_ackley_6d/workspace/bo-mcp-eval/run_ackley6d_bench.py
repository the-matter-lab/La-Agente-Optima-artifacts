#!/usr/bin/env python3
"""CLI entrypoint: 6D Ackley synthetic BO campaign via BO-MCP (BayBE backend).

Deterministic synthetic objective only - no PySCF/CREST/MOF/experimental calls.
Cache-buster nonce: f42213a0-34a7-4c2a-bbef-8b4700e0fb91
Campaign marker:    akg-eval-7f1274a8431e4c5d94a3b24374899d9e
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley6d_bench.campaign import run_campaign  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign-id", default=None, help="resume/reopen an existing campaign")
    p.add_argument("--max-evaluations", type=int, default=60,
                   help="campaign-wide attempted-evaluation budget (default 60)")
    p.add_argument("--artifacts-dir", default=None, help="default: artifacts/<UTC timestamp>")
    p.add_argument("--stop-file", default="STOP", help="touch this file to stop cleanly")
    p.add_argument("--poll-s", type=float, default=180.0, help="retry wait when no suggestions")
    p.add_argument("--heartbeat-s", type=float, default=1800.0, help="liveness print interval")
    args = p.parse_args()

    artifacts = Path(args.artifacts_dir or Path("artifacts")
                     / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    run_campaign(
        campaign_id=args.campaign_id,
        max_evaluations=args.max_evaluations,
        artifacts_dir=artifacts,
        stop_file=Path(args.stop_file),
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
    )


if __name__ == "__main__":
    main()
