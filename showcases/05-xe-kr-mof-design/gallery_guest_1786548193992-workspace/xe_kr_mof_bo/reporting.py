from __future__ import annotations

from pathlib import Path


def tagged(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
