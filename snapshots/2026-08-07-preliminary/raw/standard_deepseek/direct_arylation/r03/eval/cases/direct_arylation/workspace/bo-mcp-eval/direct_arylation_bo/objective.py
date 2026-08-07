"""Objective extraction and per-result reporting for the campaign."""

from __future__ import annotations

from typing import Any


def extract_objective_values(
    oracle_result: dict[str, Any],
) -> dict[str, float]:
    """Pull the ``yield`` value from an oracle response."""
    return {"yield": float(oracle_result["yield"])}


def format_result_line(
    attempt: int,
    params: dict[str, Any],
    status: str,
    objective_values: dict[str, float] | None,
    error: str | None,
) -> str:
    """Return a one-line ``[RESULT]`` tagged summary."""
    if status == "success" and objective_values is not None:
        y = objective_values.get("yield", float("nan"))
        return (
            f"[RESULT] attempt={attempt:03d}  yield={y:.2f}%  "
            f"base={params.get('base','?')}  "
            f"ligand={params.get('ligand','?')}  "
            f"solvent={params.get('solvent','?')}  "
            f"conc={params.get('concentration','?')}  "
            f"T={params.get('temperature_c','?')}°C"
        )
    else:
        return (
            f"[RESULT] attempt={attempt:03d}  status=FAILED  "
            f"error={error or 'unknown'}  "
            f"base={params.get('base','?')}  "
            f"ligand={params.get('ligand','?')}  "
            f"solvent={params.get('solvent','?')}  "
            f"conc={params.get('concentration','?')}  "
            f"T={params.get('temperature_c','?')}°C"
        )