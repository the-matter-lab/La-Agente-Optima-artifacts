from __future__ import annotations

import argparse
import json
from pathlib import Path

from ackley6d_campaign.campaign import Ackley6DCampaign, CampaignConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Ackley 6D synthetic BO campaign.")
    parser.add_argument("--mode", choices=["preflight", "run"], default="run")
    parser.add_argument("--seed", type=int, default=731245)
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--init-size", type=int, default=16)
    parser.add_argument("--candidate-pool-size", type=int, default=4096)
    parser.add_argument("--local-results-path", default="local_results.json")
    parser.add_argument("--table-csv-path", default="ackley6d_evaluations.csv")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = CampaignConfig(
        seed=args.seed,
        budget=args.budget,
        init_size=args.init_size,
        candidate_pool_size=args.candidate_pool_size,
        local_results_path=args.local_results_path,
        table_csv_path=args.table_csv_path,
    )
    campaign = Ackley6DCampaign(config)
    if args.mode == "preflight":
        print(json.dumps(campaign.preflight(), indent=2))
        return 0

    payload = campaign.run()
    best = payload["best_objective_value"]
    best_params = payload["best_parameters"]
    print(f"Completed {payload['attempted_evaluations']} / {payload['budget']} evaluations.")
    print(f"Best surface_response: {best:.12f}")
    print("Best normalized coordinates:")
    for key in sorted(best_params):
        print(f"  {key} = {best_params[key]:.12f}")
    print(f"Best raw_response: {payload['best_raw_response']:.12f}")
    print(f"Results artifact: {Path(config.local_results_path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
