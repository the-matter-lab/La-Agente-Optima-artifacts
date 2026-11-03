from __future__ import annotations

import argparse
import json
from pathlib import Path

from ackley6d_opt.campaign import Ackley6DCampaign, CampaignConfig, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ackley 6D Bayesian optimization runner")
    parser.add_argument("--preflight", action="store_true", help="Validate configuration without objective evaluations")
    parser.add_argument("--output", default="local_results.json", help="Results artifact path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CampaignConfig(output_path=args.output)
    write_manifest("ackley6d_opt", args.output)
    campaign = Ackley6DCampaign(config)
    if args.preflight:
        print(json.dumps(campaign.preflight_summary(), indent=2))
        return 0
    summary = campaign.run()
    best_value = summary["best_objective_value"]
    print(f"Completed {summary['attempted_evaluations']} attempted evaluations with {summary['successful_evaluations']} successes.")
    print(f"Best surface_response={best_value:.12f}")
    print(f"Results written to {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
