#!/usr/bin/env python3
"""Write a portable SHA-256 manifest for the published artifact snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPOSITORY_ROOT / "MANIFEST.sha256"
EXCLUDED_PARTS = {".git", "__pycache__"}


def main() -> None:
    files = sorted(
        path
        for path in REPOSITORY_ROOT.rglob("*")
        if path.is_file()
        and path != MANIFEST
        and not EXCLUDED_PARTS.intersection(path.parts)
    )
    lines = []
    for path in files:
        relative = path.relative_to(REPOSITORY_ROOT)
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
