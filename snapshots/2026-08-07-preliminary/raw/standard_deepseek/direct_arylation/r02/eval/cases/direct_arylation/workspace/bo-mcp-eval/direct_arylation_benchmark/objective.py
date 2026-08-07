"""Objective extraction and reporting for the direct-arylation benchmark.

Keeps an in-memory ledger of all evaluated candidates and produces the
final report.
"""

from __future__ import annotations

import json
import sys
from typing import Any


class ResultLedger:
    """Accumulates evaluation results and produces the final report."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def record(
        self,
        *,
        candidate: dict[str, Any],
        status: str,
        yield_value: float | None,
        suggestion_id: str | None = None,
        iteration: int | None = None,
    ) -> None:
        self._rows.append(
            {
                "iteration": iteration,
                "suggestion_id": suggestion_id,
                "base": candidate.get("base"),
                "ligand": candidate.get("ligand"),
                "solvent": candidate.get("solvent"),
                "concentration": candidate.get("concentration"),
                "temperature_c": candidate.get("temperature_c"),
                "status": status,
                "yield": yield_value,
            }
        )

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    @property
    def n_attempted(self) -> int:
        return len(self._rows)

    @property
    def n_successful(self) -> int:
        return sum(1 for r in self._rows if r["status"] == "success")

    @property
    def best(self) -> dict[str, Any] | None:
        successes = [r for r in self._rows if r["status"] == "success"]
        if not successes:
            return None
        return max(successes, key=lambda r: r["yield"])

    def print_final_report(self) -> None:
        best = self.best
        print("[RESULT] === Final Report ===")
        print(f"[RESULT] Attempted evaluations : {self.n_attempted}")
        print(f"[RESULT] Successful evaluations: {self.n_successful}")
        print(f"[RESULT] Failed evaluations     : {self.n_attempted - self.n_successful}")
        if best:
            print(f"[RESULT] Best yield             : {best['yield']:.2f}%")
            print(f"[RESULT] Best conditions:")
            for key in ["base", "ligand", "solvent", "concentration", "temperature_c"]:
                print(f"[RESULT]   {key}: {best[key]}")
        else:
            print("[RESULT] No successful evaluations — cannot report best yield.")
        print("[RESULT] === All evaluated candidates ===")
        for i, row in enumerate(self._rows):
            print(
                f"[RESULT] {i+1:3d}. "
                f"base={row['base']!r}  ligand={row['ligand']!r}  "
                f"solvent={row['solvent']!r}  conc={row['concentration']}  "
                f"T={row['temperature_c']}°C  "
                f"→ {row['status']}"
                + (f"  yield={row['yield']:.2f}%" if row["yield"] is not None else "")
            )

    def write_jsonl(self, path: str) -> None:
        with open(path, "a") as fh:
            for row in self._rows:
                fh.write(json.dumps(row) + "\n")