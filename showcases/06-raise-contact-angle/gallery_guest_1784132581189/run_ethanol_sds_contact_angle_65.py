from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from ethanol_sds_contact_angle_65 import CampaignConfig, run_campaign

configure_logfire()
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the clean seeded Ethanol + SDS BO/RAISE campaign to match a "
            "65 degree static contact angle target."
        )
    )
    parser.add_argument("--campaign-id", help="Resume or continue an existing BO-MCP campaign.")
    parser.add_argument(
        "--campaign-name",
        default=f"ethanol-sds-contact-angle-65-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        help="Name to use when creating a fresh campaign.",
    )
    parser.add_argument(
        "--campaign-description",
        default=(
            "RAISE static-contact-angle optimization for feasible Ethanol (0-50 v/v%) and "
            "SDS (0-1 w/v%) with a 65 degree target."
        ),
        help="Description to use when creating a fresh campaign.",
    )
    parser.add_argument(
        "--artifacts-root",
        default="artifacts",
        help="Directory where run artifacts should be written.",
    )
    parser.add_argument(
        "--manifest-path",
        default="campaign_manifest.json",
        help="Path to the campaign manifest JSON file.",
    )
    parser.add_argument(
        "--raise-timeout-s",
        type=int,
        default=500,
        help="Timeout passed to run_raise_experiment (minimum allowed by RAISE is 500).",
    )
    parser.add_argument(
        "--bo-iteration-budget",
        type=int,
        default=5,
        help="Number of BO-suggested experiments to attempt in this invocation.",
    )
    parser.add_argument(
        "--measurement-retries",
        type=int,
        default=2,
        help="How many times to retry a measurement-failure candidate before expiring the suggestion.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed stored in the BO-MCP campaign intake.",
    )
    parser.add_argument(
        "--terminate-on-exit",
        action="store_true",
        help="Terminate the campaign instead of pausing it at the end of the invocation.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = CampaignConfig(
        campaign_name=args.campaign_name,
        campaign_description=args.campaign_description,
        artifacts_root=Path(args.artifacts_root),
        campaign_id=args.campaign_id,
        manifest_path=Path(args.manifest_path),
        random_seed=args.random_seed,
        raise_timeout_s=args.raise_timeout_s,
        bo_iteration_budget=args.bo_iteration_budget,
        measurement_retries=args.measurement_retries,
        terminate_on_exit=args.terminate_on_exit,
    )
    result = run_campaign(config)
    print(f"Campaign complete: {result['campaign_id']}")
    print(f"Final status: {result['final_campaign_status']}")


if __name__ == "__main__":
    main()

