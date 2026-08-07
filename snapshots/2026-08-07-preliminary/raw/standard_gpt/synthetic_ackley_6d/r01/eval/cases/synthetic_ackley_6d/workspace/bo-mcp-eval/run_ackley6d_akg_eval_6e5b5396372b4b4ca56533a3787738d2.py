#!/usr/bin/env python
"""Run the BO-MCP Ackley 6D benchmark campaign.

Ownership marker: akg-eval-6e5b5396372b4b4ca56533a3787738d2
Cache-buster nonce: 7b86fd35-b943-4816-b7ba-82e865684bf2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire(console=False)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.campaign import RunConfig, run_campaign
from ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.intake import (
    DEFAULT_BACKEND,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_RANDOM_SEED,
)
from ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.search_space import CAMPAIGN_MARKER, TOTAL_BUDGET


DEFAULT_ARTIFACT_ROOT = "artifacts/ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2"
DEFAULT_STOP_FILE = "STOP"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", help="Existing owned campaign id to resume or reopen.")
    parser.add_argument("--campaign-label", default="main", help="Suffix included in a newly created campaign name.")
    parser.add_argument(
        "--invocation-attempt-budget",
        type=int,
        default=TOTAL_BUDGET,
        help="Maximum objective evaluations to attempt during this invocation.",
    )
    parser.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT, help="Artifact root directory.")
    parser.add_argument("--stop-file", default=DEFAULT_STOP_FILE, help="Stop marker checked before each suggestion request.")
    parser.add_argument("--poll-s", type=int, default=180, help="Polling-compatible generation timeout floor in seconds.")
    parser.add_argument("--heartbeat-s", type=int, default=1800, help="Heartbeat interval in seconds.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="BO-MCP backend to request for a new campaign.")
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED, help="Campaign random seed for new campaigns.")
    parser.add_argument(
        "--initial-design-size",
        type=int,
        default=DEFAULT_INITIAL_DESIGN_SIZE,
        help="Initial design size for new campaigns.",
    )
    return parser.parse_args()


def require_env() -> None:
    missing = [name for name in ("BO_MCP_API_URL", "BO_MCP_API_KEY") if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")


def write_manifest(summary: dict[str, str]) -> None:
    manifest = {
        "campaign_marker": CAMPAIGN_MARKER,
        "cache_buster_nonce": "7b86fd35-b943-4816-b7ba-82e865684bf2",
        "package_modules": {
            "search_space": "ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/search_space.py",
            "intake": "ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/intake.py",
            "evaluator": "ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/evaluator.py",
            "reporting": "ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/reporting.py",
            "campaign": "ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/campaign.py",
        },
        "run_entrypoint": "run_ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.py",
        "latest_artifact_dir": summary["artifact_dir"],
        "latest_campaign_id": summary["campaign_id"],
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    require_env()
    if args.invocation_attempt_budget < 0:
        raise SystemExit("--invocation-attempt-budget must be non-negative")
    if args.poll_s < 0:
        raise SystemExit("--poll-s must be non-negative")
    if args.heartbeat_s <= 0:
        raise SystemExit("--heartbeat-s must be positive")
    if args.initial_design_size <= 0:
        raise SystemExit("--initial-design-size must be positive")

    client = BoMcpClient.from_env(timeout_s=120.0)
    summary = run_campaign(
        client,
        RunConfig(
            requested_campaign_id=args.campaign_id,
            campaign_label=args.campaign_label,
            artifact_root=args.artifact_root,
            stop_file=args.stop_file,
            invocation_attempt_budget=args.invocation_attempt_budget,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            backend=args.backend,
            random_seed=args.random_seed,
            initial_design_size=args.initial_design_size,
        ),
    )
    write_manifest(summary)
    print(
        "[EVENT] Final summary: "
        f"attempted={summary['attempted_evaluations']} successful={summary['successful_evaluations']} "
        f"report={summary['report_md']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
