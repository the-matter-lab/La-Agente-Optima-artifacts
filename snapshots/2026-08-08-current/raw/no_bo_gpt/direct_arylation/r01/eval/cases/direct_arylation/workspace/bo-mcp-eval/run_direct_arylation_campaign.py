from __future__ import annotations

import argparse
import json

from direct_arylation_campaign import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct arylation yield optimization campaign")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--seed", type=int, default=818064)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()

    payload = run_campaign(budget=args.budget, seed=args.seed, preflight=args.preflight)
    if args.preflight:
        print("Preflight OK")
        print(json.dumps(payload, indent=2))
    else:
        print("Campaign complete")
        print(f"Best yield: {payload['best_objective_value']}")
        print(f"Best parameters: {json.dumps(payload['best_parameters'], ensure_ascii=False)}")
        print(f"Attempts: {payload['attempted_evaluations']} | Successes: {payload['successful_evaluations']}")


if __name__ == "__main__":
    main()
