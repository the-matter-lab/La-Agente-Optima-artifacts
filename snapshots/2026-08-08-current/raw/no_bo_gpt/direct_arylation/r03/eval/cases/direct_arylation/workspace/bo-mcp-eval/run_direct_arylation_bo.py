from __future__ import annotations

import argparse
import json
from pathlib import Path

from direct_arylation_bo.campaign import CampaignConfig, DirectArylationCampaign


def main() -> int:
    parser = argparse.ArgumentParser(description='Direct arylation BO runner')
    parser.add_argument('--results-path', default='local_results.json')
    parser.add_argument('--manifest-path', default='campaign_manifest.json')
    parser.add_argument('--seed', type=int, default=20260812)
    parser.add_argument('--budget', type=int, default=60)
    parser.add_argument('--mock', action='store_true', help='Use a local mock oracle for preflight only')
    args = parser.parse_args()

    campaign = DirectArylationCampaign(
        CampaignConfig(
            seed=args.seed,
            budget=args.budget,
            results_path=args.results_path,
            manifest_path=args.manifest_path,
        ),
        use_mock=args.mock,
    )
    summary = campaign.run()
    print(json.dumps({
        'best_objective_value': summary['best_objective_value'],
        'best_parameters': summary['best_parameters'],
        'attempted_evaluations': summary['attempted_evaluations'],
        'successful_evaluations': summary['successful_evaluations'],
        'failed_evaluations': summary['failed_evaluations'],
        'results_path': str(Path(args.results_path).resolve()),
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
