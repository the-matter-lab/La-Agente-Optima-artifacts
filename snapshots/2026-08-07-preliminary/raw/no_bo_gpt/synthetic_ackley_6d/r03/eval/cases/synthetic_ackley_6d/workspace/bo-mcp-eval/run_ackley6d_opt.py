from __future__ import annotations

import argparse
import json

try:
    import logfire
except Exception:  # pragma: no cover
    logfire = None

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # pragma: no cover
    configure_logfire = None

from ackley6d_opt.campaign import Ackley6DCampaign, CampaignConfig


LOGFIRE_READY = logfire is not None and configure_logfire is not None
if LOGFIRE_READY:
    configure_logfire()
    logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize the 6D Ackley synthetic benchmark.")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--init-size", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--acquisition-samples", type=int, default=4096)
    parser.add_argument("--results-path", default="local_results.json")
    parser.add_argument("--manifest-path", default="campaign_manifest.json")
    parser.add_argument("--case-id", default="synthetic_ackley_6d")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = CampaignConfig(
        case_id=args.case_id,
        budget=args.budget,
        init_size=args.init_size,
        seed=args.seed,
        acquisition_samples=args.acquisition_samples,
        results_path=args.results_path,
        manifest_path=args.manifest_path,
    )
    if LOGFIRE_READY:
        logfire.info("starting_ackley_campaign", budget=config.budget, seed=config.seed, init_size=config.init_size)
    payload = Ackley6DCampaign(config).run()
    best_surface = payload["best_objective_value"]
    print(f"Case: {payload['case_id']}")
    print(f"Objective: {payload['objective_name']} ({payload['objective_direction']}, {payload['objective_unit']})")
    print(f"Seed: {payload['seed']}")
    print(f"Attempted evaluations: {payload['attempted_evaluations']}")
    print(f"Successful evaluations: {payload['successful_evaluations']}")
    print("Best normalized coordinates:")
    print(json.dumps(payload["best_parameters"], indent=2))
    print(f"Best raw_response: {payload['best_raw_response']:.12f}")
    print(f"Best surface_response: {best_surface:.12f}")
    print("All evaluated candidates:")
    print(payload["results_table"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
