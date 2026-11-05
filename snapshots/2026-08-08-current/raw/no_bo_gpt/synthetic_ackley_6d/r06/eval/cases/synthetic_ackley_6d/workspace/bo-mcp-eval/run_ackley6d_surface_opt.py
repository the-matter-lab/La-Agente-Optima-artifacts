from __future__ import annotations

import argparse
import json
from pathlib import Path

from ackley6d_surface_opt.campaign import CampaignConfig, preflight, run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6D Ackley synthetic BO campaign")
    parser.add_argument("--mode", choices=["preflight", "production"], default="production")
    parser.add_argument("--output", default="local_results.json")
    args = parser.parse_args()

    config = CampaignConfig()
    if args.mode == "preflight":
        info = preflight(config)
        print(json.dumps(info, indent=2))
        return

    summary = run_campaign(config=config, output_path=args.output)
    best = summary["best_parameters"]
    print("Ackley 6D optimization completed.")
    print(f"Results artifact: {Path(args.output).resolve()}")
    print(f"Attempted evaluations: {summary['attempted_evaluations']}")
    print(f"Successful evaluations: {summary['successful_evaluations']}")
    print(f"Best raw_response: {summary['best_raw_response']:.12f}")
    print(f"Best surface_response: {summary['best_objective_value']:.12f}")
    print(
        "Best parameters: "
        + ", ".join(f"{name}={best[name]:.6f}" for name in sorted(best.keys(), key=lambda s: int(s.split('_')[1])))
    )


if __name__ == "__main__":
    main()
