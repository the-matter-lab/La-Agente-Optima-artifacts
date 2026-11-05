from __future__ import annotations

import argparse
import json
from pathlib import Path

from ackley6d_baybe.campaign import AckleyCampaignRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ackley 6D BO-MCP benchmark.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume.")
    parser.add_argument("--artifact-root", default="artifacts", help="Directory for generated artifacts.")
    parser.add_argument("--smoke-test", action="store_true", help="Validate the intake and exit without evaluations.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner = AckleyCampaignRunner(
        artifact_root=Path(args.artifact_root),
        campaign_id=args.campaign_id,
    )
    try:
        summary = runner.validate_only() if args.smoke_test else runner.run()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    finally:
        runner.close()


if __name__ == "__main__":
    raise SystemExit(main())
