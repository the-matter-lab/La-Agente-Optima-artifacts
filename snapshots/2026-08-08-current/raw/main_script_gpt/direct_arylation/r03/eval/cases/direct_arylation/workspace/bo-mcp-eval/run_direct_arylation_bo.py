from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import logfire
from grafico.core.logfire_config import configure_logfire

from direct_arylation_bo.campaign import run_campaign


def write_manifest(artifact_dir: Path) -> None:
    manifest = {
        "package_modules": [
            "direct_arylation_bo.__init__",
            "direct_arylation_bo.space",
            "direct_arylation_bo.oracle",
            "direct_arylation_bo.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_bo.py",
        "latest_artifact_dir": str(artifact_dir),
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the direct arylation BO benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Existing BO-MCP campaign id to resume/reopen.")
    parser.add_argument("--artifact-dir", default=None, help="Artifact directory. Defaults to a timestamped directory.")
    parser.add_argument("--max-attempts", type=int, required=True, help="Attempt budget for this invocation.")
    parser.add_argument("--random-seed", type=int, default=20260730, help="Campaign random seed for new campaigns.")
    parser.add_argument("--oracle-timeout-s", type=float, default=60.0, help="Per-request oracle timeout.")
    return parser.parse_args()


def main() -> None:
    configure_logfire()
    logfire.instrument_requests()

    args = parse_args()
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else Path("artifacts") / f"direct_arylation_{args.random_seed}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(artifact_dir)

    outcome = run_campaign(
        campaign_id=args.campaign_id,
        artifact_dir=artifact_dir,
        max_attempts=args.max_attempts,
        random_seed=args.random_seed,
        oracle_timeout_s=args.oracle_timeout_s,
    )
    best_line = "none"
    if outcome.best_attempt is not None:
        best_line = (
            f"yield={outcome.best_attempt['objective_values']['yield']:.2f}% "
            f"params={outcome.best_attempt['parameter_values']}"
        )
    print(f"campaign_id={outcome.campaign_id}")
    print(f"artifact_dir={outcome.artifact_dir}")
    print(f"attempts_recorded={len(outcome.attempts)}")
    print(f"successful_attempts={outcome.successful_attempts}")
    print(f"best={best_line}")


if __name__ == "__main__":
    main()
