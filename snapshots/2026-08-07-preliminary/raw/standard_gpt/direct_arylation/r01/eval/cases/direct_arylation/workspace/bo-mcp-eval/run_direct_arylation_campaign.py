from __future__ import annotations

import argparse
from pathlib import Path

import logfire

from grafico.core.logfire_config import configure_logfire

from direct_arylation_campaign.campaign import RunConfig, run_campaign

configure_logfire(console=False)
logfire.instrument_requests()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the direct arylation BO-MCP benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume or reopen.")
    parser.add_argument("--campaign-label", default=None, help="Optional suffix to place in a newly created campaign name.")
    parser.add_argument("--artifact-root", default="artifacts/direct_arylation", help="Artifact directory root.")
    parser.add_argument("--stop-file", default="STOP", help="Stop-file path checked before each suggestion generation.")
    parser.add_argument("--poll-s", type=int, default=180, help="Retry wait in seconds after suggestion-generation transport failures.")
    parser.add_argument("--heartbeat-s", type=int, default=1800, help="Heartbeat interval in seconds.")
    parser.add_argument("--max-attempts", type=int, default=60, help="Maximum attempted oracle evaluations for this campaign.")
    parser.add_argument("--oracle-timeout-s", type=float, default=30.0, help="Oracle request timeout in seconds.")
    parser.add_argument("--suggestion-timeout-s", type=float, default=900.0, help="BO suggestion generation timeout in seconds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = RunConfig(
        campaign_id=args.campaign_id,
        campaign_label=args.campaign_label,
        artifact_root=Path(args.artifact_root),
        stop_file=Path(args.stop_file),
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        max_attempts=args.max_attempts,
        oracle_timeout_s=args.oracle_timeout_s,
        suggestion_timeout_s=args.suggestion_timeout_s,
    )
    return run_campaign(config)


if __name__ == "__main__":
    raise SystemExit(main())
