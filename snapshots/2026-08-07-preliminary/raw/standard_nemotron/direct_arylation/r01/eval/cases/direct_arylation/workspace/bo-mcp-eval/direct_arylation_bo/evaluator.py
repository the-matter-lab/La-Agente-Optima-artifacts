"""Oracle evaluation module for direct arylation BO campaign."""

import json
import os
import time
from pathlib import Path
from typing import Any

from domains.direct_arylation.client import (
    DirectArylationClientError,
    evaluate_direct_arylation,
)


DEFAULT_TIMEOUT_S = 15.0


def evaluate_candidate(
    params: dict[str, Any],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> tuple[bool, float | None, str | None]:
    """
    Evaluate a single candidate via the remote oracle.

    Returns:
        (success, yield_value, error_message)
    """
    try:
        yield_value = evaluate_direct_arylation(
            base=params["base"],
            ligand=params["ligand"],
            solvent=params["solvent"],
            concentration=params["concentration"],
            temperature_c=params["temperature_c"],
            timeout_s=timeout_s,
        )
        return True, yield_value, None
    except DirectArylationClientError as exc:
        return False, None, str(exc)
    except KeyError as exc:
        return False, None, f"Missing parameter: {exc}"
    except Exception as exc:  # pragma: no cover - unexpected errors
        return False, None, f"Unexpected error: {type(exc).__name__}: {exc}"


def write_attempt_artifact(
    artifact_dir: Path,
    attempt_number: int,
    params: dict[str, Any],
    success: bool,
    yield_value: float | None,
    error_message: str | None,
) -> None:
    """Write a per-attempt artifact record."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"attempt_{attempt_number:04d}.json"

    record = {
        "attempt_number": attempt_number,
        "parameter_values": {
            "base": params["base"],
            "ligand": params["ligand"],
            "solvent": params["solvent"],
            "concentration": params["concentration"],
            "temperature_c": params["temperature_c"],
        },
        "success": success,
    }

    if success and yield_value is not None:
        record["objective_values"] = {"yield": yield_value}
    else:
        record["objective_values"] = {}
        record["error"] = error_message

    artifact_path.write_text(json.dumps(record, indent=2))