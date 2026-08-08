from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import logfire
except Exception:  # pragma: no cover
    class _FallbackLogfire:
        def instrument_requests(self) -> None:
            return None

        def info(self, *args, **kwargs) -> None:
            return None

        def debug(self, *args, **kwargs) -> None:
            return None

    logfire = _FallbackLogfire()

try:
    from grafico.core.logfire_config import configure_logfire
except Exception:  # pragma: no cover
    def configure_logfire() -> None:
        return None

from direct_arylation_bo import CampaignConfig, run_campaign

configure_logfire()
logfire.instrument_requests()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct arylation reaction-yield Bayesian optimization campaign")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--initial-random", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--pool-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--nonce", type=str, required=True)
    parser.add_argument("--output", type=str, default="local_results.json")
    parser.add_argument("--manifest", type=str, default="campaign_manifest.json")
    parser.add_argument("--smoke-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = CampaignConfig(
        cache_buster_nonce=args.nonce,
        budget=args.budget,
        initial_random=args.initial_random,
        batch_size=args.batch_size,
        pool_size=args.pool_size,
        random_seed=args.seed,
        smoke_test=args.smoke_test,
        output_path=args.output,
        manifest_path=args.manifest,
    )
    logfire.info(
        "starting_direct_arylation_campaign",
        smoke_test=config.smoke_test,
        budget=config.budget,
        initial_random=config.initial_random,
        batch_size=config.batch_size,
        pool_size=config.pool_size,
        seed=config.random_seed,
    )
    summary = run_campaign(config)
    best_value = summary["best_objective_value"]
    best_parameters = summary["best_parameters"]
    print(
        json.dumps(
            {
                "case_id": summary["case_id"],
                "smoke_test": config.smoke_test,
                "attempted_evaluations": summary["attempted_evaluations"],
                "successful_evaluations": summary["successful_evaluations"],
                "failed_evaluations": summary["failed_evaluations"],
                "best_objective_value": best_value,
                "best_parameters": best_parameters,
                "output_path": str(Path(config.output_path).resolve()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
