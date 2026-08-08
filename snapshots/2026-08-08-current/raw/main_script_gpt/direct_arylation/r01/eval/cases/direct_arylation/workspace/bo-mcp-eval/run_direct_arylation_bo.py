from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_bo.campaign import (
    DEFAULT_BACKEND,
    DEFAULT_INITIAL_DESIGN_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RANDOM_SEED,
    run_campaign,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the direct arylation BO benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume.")
    parser.add_argument("--smoke-test", action="store_true", help="Create/resume the campaign and generate exactly one pending suggestion without calling the oracle.")
    parser.add_argument("--artifact-root", default="artifacts", help="Artifact root directory under the current workspace.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="BO-MCP backend to request.")
    parser.add_argument("--initial-design-size", type=int, default=DEFAULT_INITIAL_DESIGN_SIZE)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    configure_logfire()
    logfire.instrument_requests()

    summary = run_campaign(
        workspace_root=Path.cwd(),
        artifact_root=Path(args.artifact_root),
        campaign_id=args.campaign_id,
        smoke_test=args.smoke_test,
        backend=args.backend,
        batch_size=1,
        initial_design_size=args.initial_design_size,
        max_attempts=args.max_attempts,
        random_seed=args.random_seed,
    )

    print(f"campaign_id={summary['campaign_id']}")
    print(f"artifact_dir={summary['artifact_dir']}")
    print(f"mode={summary['mode']}")
    if summary["mode"] == "production":
        print(f"attempted_evaluations={summary['attempted_evaluations']}")
        print(f"successful_evaluations={summary['successful_evaluations']}")
        best = summary.get("best_result")
        if best:
            print(f"best_yield={best['objective_values']['yield']:.2f}")


if __name__ == "__main__":
    main()
