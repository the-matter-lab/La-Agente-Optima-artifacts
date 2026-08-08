#!/usr/bin/env python3
"""Redact credential-shaped values from a copied benchmark snapshot."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPOSITORY_ROOT / "snapshots/2026-08-08-current"
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
}
ENVIRONMENT_KEYS = (
    "OPENAI|ANTHROPIC|OPENROUTER|NVIDIA|BO_MCP|DIRECT_ARYLATION"
)
JSON_ENVIRONMENT_SECRET = re.compile(
    rf'(?P<prefix>"(?:{ENVIRONMENT_KEYS})_API_KEY"\s*:\s*")'
    r'(?P<value>[^"\r\n]*)(?P<suffix>")'
)
ENVIRONMENT_ASSIGNMENT = re.compile(
    rf"(?P<prefix>(?:{ENVIRONMENT_KEYS})_API_KEY=)"
    r"(?P<value>(?!\$|\[REDACTED\])[A-Za-z0-9_./+-]{8,})"
)


def sanitize_text(text: str) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    for name, pattern in PATTERNS.items():
        text, replacements = pattern.subn("[REDACTED]", text)
        counts[name] += replacements
    text, field_replacements = JSON_ENVIRONMENT_SECRET.subn(
        lambda match: f"{match.group('prefix')}[REDACTED]{match.group('suffix')}",
        text,
    )
    text, assignment_replacements = ENVIRONMENT_ASSIGNMENT.subn(
        lambda match: f"{match.group('prefix')}[REDACTED]",
        text,
    )
    counts["environment_secret"] += field_replacements + assignment_replacements
    return text, counts


def repair_legacy_json_redaction(text: str) -> tuple[str, int]:
    """Remove quotes inserted by the original sanitizer inside JSON strings."""
    repairs = 0
    while True:
        try:
            json.loads(text)
            return text, repairs
        except json.JSONDecodeError as error:
            marker = text.rfind("[REDACTED]\"", max(0, error.pos - 5000), error.pos + 1)
            if marker < 0:
                raise
            quote = marker + len("[REDACTED]")
            text = text[:quote] + text[quote + 1 :]
            repairs += 1


def repair_structured_text(path: Path, text: str) -> tuple[str, int]:
    if path.suffix == ".json":
        return repair_legacy_json_redaction(text)
    if path.suffix != ".jsonl":
        return text, 0
    repairs = 0
    lines = []
    for line in text.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        repaired, count = repair_legacy_json_redaction(line.removesuffix("\n"))
        lines.append(repaired + ending)
        repairs += count
    return "".join(lines), repairs


def main() -> None:
    prior_report = (
        json.loads(REPORT_PATH.read_text()) if REPORT_PATH.is_file() else {}
    )
    totals: Counter[str] = Counter()
    changed_files: dict[str, dict[str, int]] = {}
    for path in sorted(SNAPSHOT.rglob("*")):
        if not path.is_file() or path == REPORT_PATH:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        repaired, repair_count = repair_structured_text(path, original)
        sanitized, counts = sanitize_text(repaired)
        counts["legacy_json_repair"] += repair_count
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
        "history": prior_report.get("history", []),
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
