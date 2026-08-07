#!/usr/bin/env python
"""Run the BO-MCP synthetic Ackley 6D benchmark campaign.

User nonce: 955b0c73-e93c-475f-b0fc-19ad0dfdc1ea
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley_bomcp_benchmark.campaign import run_campaign
from ackley_bomcp_benchmark.intake import CAMPAIGN_MARKER, TOTAL_ATTEMPT_BUDGET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", help="Existing owned campaign id to resume/reopen.")
    parser.add_argument(
        "--invocation-attempt-budget",
        type=int,
        default=TOTAL_ATTEMPT_BUDGET,
        help="Maximum unique local objective evaluations to attempt during this invocation.",
    )
    parser.add_argument("--poll-s", type=int, default=180, help="Reserved for monitor compatibility.")
    parser.add_argument("--heartbeat-s", type=int, default=1800, help="Heartbeat interval in seconds.")
    parser.add_argument("--stop-file", default="STOP", help="Stop marker file checked before each suggestion request.")
    parser.add_argument(
        "--artifact-root",
        default="artifacts/ackley_bomcp_benchmark",
        help="Directory where campaign-specific artifacts are written.",
    )
    return parser.parse_args()


def require_env() -> None:
    missing = [name for name in ("BO_MCP_API_URL", "BO_MCP_API_KEY") if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")


def write_manifest(summary: dict[str, str]) -> None:
    manifest = {
        "campaign_marker": CAMPAIGN_MARKER,
        "package_modules": {
            "search_space": "ackley_bomcp_benchmark/search_space.py",
            "intake": "ackley_bomcp_benchmark/intake.py",
            "evaluator": "ackley_bomcp_benchmark/evaluator.py",
            "reporting": "ackley_bomcp_benchmark/reporting.py",
            "campaign": "ackley_bomcp_benchmark/campaign.py",
        },
        "run_entrypoint": "run_ackley_bomcp_benchmark.py",
        "latest_artifact_dir": summary["artifact_dir"],
        "latest_campaign_id": summary["campaign_id"],
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    require_env()
    if args.invocation_attempt_budget < 0:
        raise SystemExit("--invocation-attempt-budget must be non-negative")
    if args.poll_s < 0 or args.heartbeat_s <= 0:
        raise SystemExit("--poll-s must be non-negative and --heartbeat-s must be positive")

    client = BoMcpClient.from_env(timeout_s=120.0)
    summary = run_campaign(
        client=client,
        requested_campaign_id=args.campaign_id,
        invocation_attempt_budget=args.invocation_attempt_budget,
        stop_file=args.stop_file,
        heartbeat_s=args.heartbeat_s,
        artifact_root=args.artifact_root,
    )
    write_manifest(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
