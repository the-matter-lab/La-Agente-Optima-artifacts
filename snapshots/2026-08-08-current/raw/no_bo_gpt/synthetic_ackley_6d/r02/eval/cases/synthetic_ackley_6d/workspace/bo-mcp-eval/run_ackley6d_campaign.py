from __future__ import annotations

import argparse
import json

from ackley6d_campaign.campaign import CampaignConfig, run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local BO on the 6D Ackley synthetic surface.")
    parser.add_argument("--mode", choices=["smoke", "production"], default="production")
    parser.add_argument("--results-path", default="local_results.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "smoke":
        config = CampaignConfig(
            case_id="synthetic_ackley_6d_smoke",
            total_budget=6,
            init_size=4,
            batch_schedule=[2],
            random_seed=20260731,
            candidate_pool_size=512,
            gp_restarts=1,
            results_path=args.results_path,
        )
    else:
        config = CampaignConfig(
            case_id="synthetic_ackley_6d",
            total_budget=60,
            init_size=12,
            batch_schedule=[4] * 12,
            random_seed=20260730,
            candidate_pool_size=4096,
            gp_restarts=3,
            results_path=args.results_path,
        )
    payload = run_campaign(config)
    print(json.dumps(
        {
            "case_id": payload["case_id"],
            "attempted_evaluations": payload["attempted_evaluations"],
            "successful_evaluations": payload["successful_evaluations"],
            "best_objective_value": payload["best_objective_value"],
            "best_parameters": payload["best_parameters"],
            "best_raw_response": payload["best_raw_response"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
