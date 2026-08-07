"""Attempt tracking artifact for direct arylation BO-MCP campaign.

Tracks all 60 attempted oracle evaluations (including failures) across resumes.
Uses a JSONL file for append-only provenance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ATTEMPTS_FILENAME = "attempts.jsonl"


def get_attempts_path(campaign_id: str, workspace: Path | None = None) -> Path:
    """Get the path to the attempts artifact file for a campaign."""
    if workspace is None:
        workspace = Path.cwd()
    # Store in a subdirectory named after the campaign
    artifact_dir = workspace / "artifacts" / campaign_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir / ATTEMPTS_FILENAME


def load_attempts(campaign_id: str, workspace: Path | None = None) -> list[dict[str, Any]]:
    """Load all attempts from the artifact file."""
    path = get_attempts_path(campaign_id, workspace)
    if not path.exists():
        return []
    
    attempts = []
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                attempts.append(json.loads(line))
    return attempts


def append_attempt(campaign_id: str, attempt: dict[str, Any], workspace: Path | None = None) -> None:
    """Append a single attempt to the artifact file."""
    path = get_attempts_path(campaign_id, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(attempt) + "\n")


def count_attempts(campaign_id: str, workspace: Path | None = None) -> int:
    """Count total attempts (including failed) for a campaign."""
    return len(load_attempts(campaign_id, workspace))


def get_attempt_history(campaign_id: str, workspace: Path | None = None) -> list[dict[str, Any]]:
    """Get full attempt history for reporting."""
    return load_attempts(campaign_id, workspace)