#!/usr/bin/env python3
"""Recovery entrypoint: rebuild local results.csv/results.jsonl for an
existing Ackley-6D BO-MCP campaign authoritatively from server state.

Read-only against campaign lifecycle: never creates, resumes, reopens, or
pauses the campaign, and never submits results/suggestions. Only rewrites
the local artifact files. Safe to re-run any number of times.

Usage:
    uv run python recover_ackley6d_bo.py --campaign-id <BO_MCP_CAMPAIGN_ID>

Context nonce (preserve exactly): 1bc98eae-1366-4f95-ba15-243c959b907b
"""

import argparse
from pathlib import Path

import logfire

from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient

from ackley6d_bo import reporting
from ackley6d_bo.recovery import rebuild_artifacts_from_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Ackley-6D BO-MCP local artifacts from server state.")
    parser.add_argument("--campaign-id", required=True, help="Existing campaign id to reconstruct artifacts for.")
    parser.add_argument("--artifact-dir", default="ackley6d_bo_artifacts", help="Directory holding results.csv/results.jsonl.")
    args = parser.parse_args()

    client = BoMcpClient.from_env()
    print(f"[EVENT] rebuilding artifacts for campaign {args.campaign_id} from server state", flush=True)
    rows = rebuild_artifacts_from_server(client, args.campaign_id, Path(args.artifact_dir))

    successful = sum(1 for r in rows if r["status"] == "success")
    failed = len(rows) - successful
    print(f"[EVENT] rebuilt {len(rows)} rows (successful={successful}, failed={failed})", flush=True)

    best = max((r for r in rows if r["status"] == "success"), key=lambda r: r["surface_response"], default=None)
    reporting.print_final_summary(args.campaign_id, len(rows), successful, best)


if __name__ == "__main__":
    main()
