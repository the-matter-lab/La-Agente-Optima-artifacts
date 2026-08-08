from __future__ import annotations

import argparse
import json

from direct_arylation_bo.campaign import build_config, run_campaign

try:
    import logfire
    from grafico.core.logfire_config import configure_logfire
    configure_logfire()
    logfire.instrument_requests()
except Exception:  # noqa: BLE001
    class _FallbackLogfire:
        @staticmethod
        def info(*args, **kwargs):
            return None
    logfire = _FallbackLogfire()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct arylation local Bayesian optimization runner")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--cache-buster-nonce", type=str, default="")
    parser.add_argument("--results-path", type=str, default="local_results.json")
    parser.add_argument("--manifest-path", type=str, default="campaign_manifest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = build_config(
        budget=args.budget,
        seed=args.seed,
        smoke_test=args.smoke_test,
        cache_buster_nonce=args.cache_buster_nonce,
        results_path=args.results_path,
        manifest_path=args.manifest_path,
    )
    logfire.info(
        "starting direct arylation campaign",
        budget=config.budget,
        smoke_test=config.smoke_test,
        seed=config.seed,
    )
    payload = run_campaign(config)
    best_value = payload["best_objective_value"]
    print(
        json.dumps(
            {
                "case_id": payload["case_id"],
                "attempted_evaluations": payload["attempted_evaluations"],
                "successful_evaluations": payload["successful_evaluations"],
                "failed_evaluations": payload["failed_evaluations"],
                "best_objective_value": best_value,
                "best_parameters": payload["best_parameters"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
