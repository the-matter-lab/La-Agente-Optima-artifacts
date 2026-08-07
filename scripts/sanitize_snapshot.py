#!/usr/bin/env python3
"""Redact credential-shaped values from a copied benchmark snapshot."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPOSITORY_ROOT / "snapshots/2026-08-07-preliminary"
REPORT_PATH = SNAPSHOT / "SANITIZATION_REPORT.json"
PATTERNS = {
    "openai_or_anthropic_key": re.compile(
        r"(?:sk-ant-|sk-or-v1-|sk-proj-|sk-)[A-Za-z0-9_-]{16,}"
    ),
    "github_token": re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "nvidia_key": re.compile(r"nvapi-[A-Za-z0-9_-]{16,}"),
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "environment_secret": re.compile(
        r"(?P<name>(?:OPENAI|ANTHROPIC|OPENROUTER|NVIDIA|BO_MCP|DIRECT_ARYLATION)_API_KEY)"
        r"(?P<separator>[\"']?\s*[:=]\s*[\"']?)(?P<value>[^\"'\s,}]+)"
    ),
}


def sanitize_text(text: str) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    for name, pattern in PATTERNS.items():
        if name == "environment_secret":
            text, replacements = pattern.subn(
                lambda match: (
                    f"{match.group('name')}{match.group('separator')}[REDACTED]"
                ),
                text,
            )
        else:
            text, replacements = pattern.subn("[REDACTED]", text)
        counts[name] += replacements
    return text, counts


def main() -> None:
    totals: Counter[str] = Counter()
    changed_files: dict[str, dict[str, int]] = {}
    for path in sorted(SNAPSHOT.rglob("*")):
        if not path.is_file() or path == REPORT_PATH:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        sanitized, counts = sanitize_text(original)
        if sanitized == original:
            continue
        path.write_text(sanitized, encoding="utf-8")
        relative = str(path.relative_to(REPOSITORY_ROOT))
        changed_files[relative] = dict(counts)
        totals.update(counts)
    payload = {
        "snapshot": str(SNAPSHOT.relative_to(REPOSITORY_ROOT)),
        "changed_file_count": len(changed_files),
        "replacement_counts": dict(totals),
        "changed_files": changed_files,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
