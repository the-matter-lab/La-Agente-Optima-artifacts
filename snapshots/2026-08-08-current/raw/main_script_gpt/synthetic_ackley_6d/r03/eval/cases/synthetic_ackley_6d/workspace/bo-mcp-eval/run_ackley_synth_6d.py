from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import logfire
from grafico.core.logfire_config import configure_logfire

from ackley_synth_6d.campaign import AckleyCampaignRunner, AckleyRunConfig

configure_logfire()
logfire.instrument_requests()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the 6D Ackley BO-MCP benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to continue.")
    parser.add_argument("--total-budget", type=int, default=60, help="Total attempted evaluation budget.")
    parser.add_argument("--default-batch-size", type=int, default=4, help="Nominal BO batch size.")
    parser.add_argument("--initial-design-size", type=int, default=16, help="Warm-start design size.")
    parser.add_argument("--acquisition-method", default="noisy_expected_improvement")
    parser.add_argument("--backend", default="botorch")
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--max-batches", type=int, default=None, help="Optional per-invocation batch cap.")
    parser.add_argument("--invocation-label", default="production")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_kwargs = {
        "total_budget": args.total_budget,
        "default_batch_size": args.default_batch_size,
        "initial_design_size": args.initial_design_size,
        "acquisition_method": args.acquisition_method,
        "backend": args.backend,
        "max_batches": args.max_batches,
        "invocation_label": args.invocation_label,
    }
    if args.random_seed is not None:
        config_kwargs["random_seed"] = args.random_seed
    config = AckleyRunConfig(**config_kwargs)
    runner = AckleyCampaignRunner(config=config, workspace=Path.cwd())
    summary = runner.run(campaign_id=args.campaign_id)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
