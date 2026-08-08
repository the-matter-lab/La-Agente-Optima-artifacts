from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import logfire

sys.path.insert(0, "/app")

from grafico.core.logfire_config import configure_logfire  # noqa: E402

from ackley_synth_6d.campaign import MARKER, run_campaign  # noqa: E402


def _utcstamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _default_artifact_dir() -> Path:
    manifest_path = Path("campaign_manifest.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        latest = manifest.get("latest_artifact_dir")
        if latest:
            return Path(latest)
    return Path("artifacts") / f"ackley_synth_6d_{_utcstamp()}"


def _write_manifest(artifact_dir: Path) -> None:
    manifest = {
        "campaign_slug": "ackley_synth_6d",
        "marker": MARKER,
        "package_modules": [
            "ackley_synth_6d.__init__",
            "ackley_synth_6d.objective",
            "ackley_synth_6d.campaign",
        ],
        "run_entrypoint": "run_ackley_synth_6d.py",
        "latest_artifact_dir": str(artifact_dir),
    }
    Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Ackley synthetic 6D BO benchmark.")
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--artifact-dir", default=None)
    parser.add_argument("--max-new-evaluations", type=int, default=None)
    args = parser.parse_args()

    configure_logfire()
    logfire.instrument_requests()

    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else _default_artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(artifact_dir)

    result = run_campaign(
        nonce=args.nonce,
        artifact_dir=artifact_dir,
        campaign_id=args.campaign_id,
        max_new_evaluations=args.max_new_evaluations,
    )
    output_path = artifact_dir / "run_result.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"CAMPAIGN_ID={result['campaign_id']}")
    print(f"ARTIFACT_DIR={artifact_dir}")
    print(f"SUMMARY_JSON={artifact_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
