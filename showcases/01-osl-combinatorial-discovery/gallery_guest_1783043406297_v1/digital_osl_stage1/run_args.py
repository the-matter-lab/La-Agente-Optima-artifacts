from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or execute Stage 1 of a bounded BO-MCP + PySCF digital OSL campaign over A-B-C-B-A fragment assemblies. "
            "Default mode is preview-only for safe parameter review."
        )
    )
    parser.add_argument("--execute", action="store_true", help="Create/attach campaign and run the bounded Stage 1 loop.")
    parser.add_argument("--campaign-id", type=str, default=None, help="Attach to an existing BO-MCP campaign id.")
    parser.add_argument("--campaign-name", type=str, default="digital-osl-stage1", help="Campaign name for fresh creates.")
    parser.add_argument("--campaign-description", type=str, default=(
        "Stage 1 bounded, cheap, first-pass digital OSL campaign over fragment-assembled A-B-C-B-A molecules. "
        "Uses CREST/GFN-FF plus cheap TDDFT/PBE/def2-SVP without geometry optimization or frequency validation."
    ))
    parser.add_argument("--cap-catalog", type=Path, default=Path("adk9227_data_s1.csv"))
    parser.add_argument("--bridge-catalog", type=Path, default=Path("adk9227_data_s2.csv"))
    parser.add_argument("--core-catalog", type=Path, default=Path("adk9227_data_s3.csv"))
    parser.add_argument("--validation-catalog", type=Path, default=Path("adk9227_data_s6.csv"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts") / "digital_osl_stage1")
    parser.add_argument("--skip-bo-validate", action="store_true", help="Skip BO-MCP validate_intake in preview or before create.")
    parser.add_argument("--backend", type=str, default="baybe", choices=["baybe", "auto", "botorch"])
    parser.add_argument("--allow-plain-categorical-fallback", action="store_true", help="If BayBE custom descriptors are rejected at validate_intake, retry preview/create with plain categorical parameters.")
    parser.add_argument("--random-seed", type=int, default=9227)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--cap-limit", type=int, default=6)
    parser.add_argument("--bridge-limit", type=int, default=6)
    parser.add_argument("--core-limit", type=int, default=10)
    parser.add_argument("--initial-observation-count", type=int, default=4)
    parser.add_argument("--seed-diversity-pool", type=int, default=4)
    parser.add_argument("--max-successful-evaluations", type=int, default=6)
    parser.add_argument("--max-runtime-minutes", type=int, default=180)
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
    parser.add_argument("--evaluation-backend", type=str, default="digital", choices=["digital", "synthetic"], help="Synthetic mode is intended for BO-loop smoke testing only.")
    parser.add_argument("--terminate-on-exit", action="store_true", help="Terminate instead of pause when the invocation finishes.")
    parser.add_argument("--export-format", type=str, default="csv")
    parser.add_argument("--run-label", type=str, default=None)
    namespace = parser.parse_args(argv)
    payload = vars(namespace)
    payload["validate_with_bo_api"] = not payload.pop("skip_bo_validate")
    return payload
