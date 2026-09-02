from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    ensure_dir(path.parent)
    frame.to_csv(path, index=False)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def write_export(path_base: Path, content: bytes, content_type: str) -> Path:
    ensure_dir(path_base.parent)
    suffix = ".csv" if "csv" in content_type else ".txt" if "text" in content_type else ".bin"
    target = path_base.with_suffix(suffix)
    target.write_bytes(content)
    return target


def concise_preview_text(summary: dict[str, Any]) -> str:
    counts = summary["active_fragment_counts"]
    initial_ids = [item["candidate_id"] for item in summary["initial_candidates"]]
    descriptor_columns = summary["descriptor_columns"]
    initial_line = ", ".join(initial_ids) if initial_ids else "(none)"
    return "\n".join(
        [
            "Preview prepared successfully.",
            f"Active caps/bridges/cores: {counts['caps']}/{counts['bridges']}/{counts['cores']}",
            f"Candidate count: {counts['candidate_count']}",
            f"Initial candidates: {initial_line}",
            f"Descriptor columns: {descriptor_columns}",
        ]
    )
