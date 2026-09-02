from __future__ import annotations

import csv
import json
from pathlib import Path

from .library import build_library, library_summary


def print_tag(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def write_library_report(artifacts_dir: Path) -> Path:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    lib = build_library()
    summary = library_summary()
    json_path = artifacts_dir / "candidate_library.json"
    csv_path = artifacts_dir / "candidate_library.csv"
    json_path.write_text(json.dumps({"summary": summary, "candidates": [c.asdict() for c in lib]}, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(lib[0].asdict().keys()))
        writer.writeheader()
        for cand in lib:
            writer.writerow(cand.asdict())
    return json_path


def report_library(artifacts_dir: Path) -> None:
    path = write_library_report(artifacts_dir)
    summary = library_summary()
    print_tag(
        "EVENT",
        "candidate library constructed before calculations: "
        f"total={summary['total_candidates']}; per_linker={summary['candidates_per_linker']}; "
        f"symmetric={summary['symmetric_R1_eq_R2']}; unsymmetric={summary['unsymmetric_R1_neq_R2']}; "
        f"duplicate_ids={summary['duplicate_candidate_ids']}; "
        f"duplicate_R1_R2_permutations_remaining={summary['duplicate_R1_R2_permutations_remaining']}; "
        f"report={path.as_posix()}",
    )


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
