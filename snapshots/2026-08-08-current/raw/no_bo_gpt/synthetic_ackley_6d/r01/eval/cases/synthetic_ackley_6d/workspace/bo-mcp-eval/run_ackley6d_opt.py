from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import logfire
    from grafico.core.logfire_config import configure_logfire

    configure_logfire()
    logfire.instrument_requests()
except Exception:  # pragma: no cover
    logfire = None

from ackley6d_opt.campaign import CampaignConfig, run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Ackley 6D synthetic BO campaign")
    parser.add_argument("--case-id", default="synthetic_ackley_6d")
    parser.add_argument("--cache-buster-nonce", required=True)
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--initial-design-size", type=int, default=11)
    parser.add_argument("--candidate-pool-size", type=int, default=8192)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--output", default="local_results.json")
    args = parser.parse_args()

    config = CampaignConfig(
        case_id=args.case_id,
        cache_buster_nonce=args.cache_buster_nonce,
        budget=args.budget,
        initial_design_size=args.initial_design_size,
        candidate_pool_size=args.candidate_pool_size,
        seed=args.seed,
        output_path=args.output,
    )

    if logfire is not None:
        logfire.info(
            "starting_ackley_campaign",
            case_id=config.case_id,
            budget=config.budget,
            initial_design_size=config.initial_design_size,
            seed=config.seed,
        )

    artifact = run_campaign(config)

    manifest = {
        "package_modules": [
            "ackley6d_opt/__init__.py",
            "ackley6d_opt/objective.py",
            "ackley6d_opt/bo.py",
            "ackley6d_opt/campaign.py",
        ],
        "run_entrypoint": "run_ackley6d_opt.py",
        "latest_local_results": str(Path(args.output).resolve()),
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    best = artifact["best_objective_value"]
    best_raw = artifact["best_raw_response"]
    best_params = artifact["best_parameters"]
    print(f"case_id={artifact['case_id']}")
    print(f"attempted_evaluations={artifact['attempted_evaluations']}")
    print(f"successful_evaluations={artifact['successful_evaluations']}")
    print(f"best_surface_response={best:.12f}")
    print(f"best_raw_response={best_raw:.12f}")
    print("best_parameters=" + json.dumps(best_params, sort_keys=True))
    print(f"results_path={Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
