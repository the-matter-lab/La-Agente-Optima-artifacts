from __future__ import annotations

import argparse
import json
from pathlib import Path

from ackley_surface_6d.campaign import AckleyBenchmarkRunner, build_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the 6D Ackley BO-MCP benchmark campaign.")
    parser.add_argument("--campaign-id", default=None, help="Resume or continue an existing campaign id.")
    parser.add_argument("--evaluation-budget", type=int, default=60, help="Attempted evaluation budget for this invocation.")
    parser.add_argument("--artifact-root", default="artifacts", help="Workspace-relative directory for campaign artifacts.")
    parser.add_argument("--smoke-test", action="store_true", help="Create a smoke-test campaign and run a single BO iteration budget.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workspace = Path.cwd()
    artifact_root = (workspace / args.artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    settings = build_settings(evaluation_budget=args.evaluation_budget, smoke_test=args.smoke_test)
    runner = AckleyBenchmarkRunner(workspace=workspace, artifact_root=artifact_root, settings=settings)
    campaign_id = runner.ensure_campaign(args.campaign_id)
    runner.prepare_artifacts(campaign_id)
    runner.load_existing_results(campaign_id)
    summary = runner.run()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
