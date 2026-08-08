"""Artifact logging and objective extraction for the Ackley benchmark.

Writes one JSONL row per evaluated candidate to an append-only artifact
file.  Also provides helpers to format per-iteration tagged stdout lines.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


def init_artifact_dir(artifact_dir: str) -> str:
    """Create the artifact directory and return its absolute path."""
    os.makedirs(artifact_dir, exist_ok=True)
    return os.path.abspath(artifact_dir)


def log_result(artifact_dir: str, row: dict[str, Any], index: int) -> None:
    """Append one evaluated-candidate row to the JSONL artifact."""
    record = {
        "evaluation_index": index,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "parameter_values": row.get("parameter_values", {}),
        "objective_values": row.get("objective_values", {}),
        "raw_response": row.get("raw_response"),
        "status": row.get("status", "unknown"),
        "failure_reason": row.get("failure_reason", ""),
    }
    path = os.path.join(artifact_dir, "evaluations.jsonl")
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def emit_event(msg: str) -> None:
    _tagged("EVENT", msg)


def emit_alert(msg: str) -> None:
    _tagged("ALERT", msg)


def emit_result(
    index: int,
    params: dict[str, float],
    surface: float | None,
    raw: float | None,
    status: str,
) -> None:
    if status == "success":
        _tagged(
            "RESULT",
            f"eval={index} surface_response={surface:.6f} "
            + " ".join(f"{k}={v:.4f}" for k, v in params.items()),
        )
    else:
        _tagged("RESULT", f"eval={index} status={status}")


def emit_heartbeat(msg: str) -> None:
    _tagged("HEARTBEAT", msg)


def _tagged(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)
    # Also write to the run log if LOG_PATH is set
    log_path = os.environ.get("LOG_PATH")
    if log_path:
        with open(log_path, "a") as fh:
            fh.write(f"[{tag}] {msg}\n")