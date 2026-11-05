from __future__ import annotations

import argparse
import json
import sys

import logfire

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # noqa: BLE001
    def configure_logfire() -> None:
        return None

from direct_arylation_bo.campaign import DirectArylationCampaign, load_config_from_env


CASE_ID = "direct_arylation_yield_optimization__ee5cbbdd-e533-43fa-91aa-c0d4b0a6c9c4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct arylation reaction-yield BO campaign")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--output", default="local_results.json")
    parser.add_argument("--preflight", action="store_true", help="Run a non-objective dry preflight")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logfire()
    logfire.instrument_requests()
    live = not args.preflight
    if args.budget <= 0:
        raise SystemExit("budget must be positive")
    config = load_config_from_env(
        live=live,
        budget=args.budget,
        seed=args.seed,
        output_path=args.output,
        case_id=CASE_ID,
    )
    campaign = DirectArylationCampaign(config)
    artifact = campaign.run()
    best = artifact["best_objective_value"]
    print(
        json.dumps(
            {
                "case_id": artifact["case_id"],
                "attempted_evaluations": artifact["attempted_evaluations"],
                "completed_evaluations": artifact["completed_evaluations"],
                "failed_evaluations": artifact["failed_evaluations"],
                "best_objective_value": best,
                "best_parameters": artifact["best_parameters"],
                "mode": "live" if live else "preflight",
                "output": args.output,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
