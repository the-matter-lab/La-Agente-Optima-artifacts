from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or execute the Stage 1b digital OSL BO-MCP + PySCF campaign. "
            "Default mode is preview-only so the expanded superset space and legacy import plan can be reviewed safely."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Create/attach the Stage 1b campaign and run the bounded BO loop.")
    parser.add_argument("--campaign-id", type=str, default=None, help="Attach to an existing Stage 1b BO-MCP campaign id.")
    parser.add_argument("--campaign-name", type=str, default="digital-osl-stage1b", help="Campaign name for fresh creates.")
    parser.add_argument(
        "--campaign-description",
        type=str,
        default=(
            "Stage 1b digital OSL campaign with a deterministic frontier-aware expansion of the original Stage 1 "
            "fragment space. Uses imported Stage 1 observations plus CREST/GFN-FF and cheap TDDFT/PBE/def2-SVP "
            "evaluation without geometry optimization or frequency validation."
        ),
    )
    parser.add_argument("--cap-catalog", type=Path, default=Path("adk9227_data_s1.csv"))
    parser.add_argument("--bridge-catalog", type=Path, default=Path("adk9227_data_s2.csv"))
    parser.add_argument("--core-catalog", type=Path, default=Path("adk9227_data_s3.csv"))
    parser.add_argument("--validation-catalog", type=Path, default=Path("adk9227_data_s6.csv"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts") / "digital_osl_stage1b")
    parser.add_argument("--skip-bo-validate", action="store_true", help="Skip BO-MCP validate_intake in preview or before create.")
    parser.add_argument("--backend", type=str, default="baybe", choices=["baybe", "auto", "botorch"])
    parser.add_argument(
        "--allow-plain-categorical-fallback",
        action="store_true",
        help="If BayBE custom descriptors are rejected at validate_intake, retry with plain categorical parameters.",
    )
    parser.add_argument("--random-seed", type=int, default=9227)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--cap-target", type=int, default=12)
    parser.add_argument("--bridge-target", type=int, default=12)
    parser.add_argument("--core-target", type=int, default=18)
    parser.add_argument(
        "--legacy-campaign-id",
        type=str,
        default="03cd5601-f16d-4e76-a588-7d15bf8268cb",
        help="Stage 1 campaign id recorded for provenance in imported observations.",
    )
    parser.add_argument(
        "--legacy-export-csv",
        type=Path,
        default=Path("artifacts") / "digital_osl_stage1" / "20260703T031540Z_execute" / "campaign_export.csv",
        help="CSV export containing successful Stage 1 observations to import into Stage 1b.",
    )
    parser.add_argument("--expected-legacy-successes", type=int, default=16)
    parser.add_argument("--skip-legacy-import", action="store_true", help="Do not import prior Stage 1 observations into the Stage 1b campaign.")
    parser.add_argument("--max-new-bo-successes", type=int, default=30, help="Per-invocation BO evaluation budget after legacy imports.")
    parser.add_argument("--max-runtime-minutes", type=int, default=1440)
    parser.add_argument("--target-energy-ev", type=float, default=2.65)
    parser.add_argument("--low-state-window", type=int, default=5)
    parser.add_argument("--ambiguity-window-kcal", type=float, default=2.0)
    parser.add_argument("--tddft-nstates", type=int, default=6)
    parser.add_argument("--basis-set", type=str, default="def2-SVP")
    parser.add_argument("--xc-functional", type=str, default="PBE")
    parser.add_argument("--crest-method", type=str, default="gfnff")
    parser.add_argument("--crest-threads", type=int, default=8)
    parser.add_argument("--pyscf-timeout-s", type=int, default=900)
    parser.add_argument("--evaluation-timeout-s", type=int, default=1200)
    parser.add_argument(
        "--evaluation-backend",
        type=str,
        default="digital",
        choices=["digital", "synthetic"],
        help="Synthetic mode is intended for BO-loop smoke testing only.",
    )
    parser.add_argument("--terminate-on-exit", action="store_true", help="Terminate instead of pause when the invocation finishes.")
    parser.add_argument("--export-format", type=str, default="csv")
    parser.add_argument("--run-label", type=str, default=None)
    namespace = parser.parse_args(argv)
    payload = vars(namespace)
    payload["validate_with_bo_api"] = not payload.pop("skip_bo_validate")
    return payload
