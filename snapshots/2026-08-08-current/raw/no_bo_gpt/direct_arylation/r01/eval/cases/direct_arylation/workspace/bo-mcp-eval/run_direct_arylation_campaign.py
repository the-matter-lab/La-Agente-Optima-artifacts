from __future__ import annotations

import argparse
import hashlib

from direct_arylation_campaign import CampaignConfig, run_campaign


def _default_seed_from_nonce(nonce: str) -> int:
    if not nonce:
        return 20260730
    return int(hashlib.sha256(nonce.encode("utf-8")).hexdigest()[:8], 16)


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize direct arylation yield over a fixed search space.")
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--n-initial", type=int, default=12)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="local_results.json")
    parser.add_argument("--manifest", default="campaign_manifest.json")
    parser.add_argument(
        "--cache-buster-nonce",
        default="9be503fc-ec3e-4db1-9e94-53bcf920f41e",
    )
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else _default_seed_from_nonce(args.cache_buster_nonce)
    config = CampaignConfig(
        budget=args.budget,
        n_initial=args.n_initial,
        seed=seed,
        dry_run=args.dry_run,
        output_path=args.output,
        manifest_path=args.manifest,
        cache_buster_nonce=args.cache_buster_nonce,
    )
    run_campaign(config)


if __name__ == "__main__":
    main()
