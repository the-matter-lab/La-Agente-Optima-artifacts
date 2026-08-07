#!/usr/bin/env python3
"""Re-audit the global 60-evaluation budget from frozen PostgreSQL dumps."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path("/local-scratch/home/lynnfang00/research")
CLAUDE_ROOT = RESEARCH / "akg4pyscf-claude5-baybe-extension-20260805"
MATRIX_ROOT = (
    RESEARCH
    / "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "full_matrix_20260730T154405Z"
)
NEMOTRON_ROOT = (
    RESEARCH
    / "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "nemotron_extension_20260803T171418Z"
)
GPT56_ROOT = (
    RESEARCH
    / "akg4pyscf-gpt56-baybe-extension-20260804/outputs/bo_mcp_evals/"
    "gpt56_baybe_extension_20260805T025700Z"
)
SONNET_ROOT = (
    CLAUDE_ROOT
    / "outputs/bo_mcp_evals/claude_sonnet5_baybe_extension_20260805T215935Z"
)
OPUS_ROOT = (
    CLAUDE_ROOT
    / "outputs/bo_mcp_evals/claude_opus5_baybe_extension_20260805T215935Z"
)
OUTPUT = ROOT / "control/GLOBAL_BUDGET_AUDIT.json"
EXPECTED_OBJECTIVES = {
    "synthetic_ackley_6d": {"surface_response"},
    "direct_arylation": {"yield"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_dump(directory: Path) -> Path:
    dumps = sorted(directory.glob("*.dump"))
    if not dumps:
        raise FileNotFoundError(f"no database dump in {directory}")
    return dumps[-1]


def _dump_rows(dump_path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    restored = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{dump_path}:/dump:ro",
            "postgres:16-alpine",
            "pg_restore",
            "-a",
            "-t",
            "campaigns",
            "-t",
            "results",
            "-f",
            "-",
            "/dump",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    table: str | None = None
    columns: list[str] = []
    campaigns: dict[str, dict[str, str]] = {}
    results: list[dict[str, str]] = []
    for line in restored.splitlines():
        if line.startswith("COPY public."):
            table = line.split()[1].split(".")[1]
            columns = line[line.index("(") + 1 : line.index(")")].split(", ")
            continue
        if line == r"\.":
            table = None
            continue
        if table is None or not line or line.startswith("--"):
            continue
        values = line.split("\t")
        if len(values) != len(columns):
            raise ValueError(f"malformed {table} COPY row in {dump_path}")
        row = dict(zip(columns, values, strict=True))
        if table == "campaigns":
            campaigns[row["id"]] = row
        elif table == "results" and row["deleted_at"] == r"\N":
            results.append(row)
    return campaigns, results


def _canonical_json(raw: str) -> str | None:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _arm_sources() -> list[tuple[str, Path, Path]]:
    matrix_audit = MATRIX_ROOT / "control/FULL_MATRIX_AUDIT.json"
    sources = [
        (
            arm_id,
            matrix_audit,
            MATRIX_ROOT / f"arms/{arm_id}/control/database_snapshots",
        )
        for arm_id in (
            "standard_gpt",
            "standard_glm",
            "standard_gemini",
            "standard_deepseek",
            "main_script_gpt",
            "direct_tool_gpt",
            "no_bo_gpt",
        )
    ]
    sources.extend(
        [
            (
                "standard_nemotron",
                NEMOTRON_ROOT / "control/NEMOTRON_EXTENSION_AUDIT.json",
                NEMOTRON_ROOT
                / "arms/standard_nemotron/control/database_snapshots",
            ),
            (
                "standard_gpt56",
                GPT56_ROOT / "control/EXTENSION_AUDIT.json",
                GPT56_ROOT / "arms/standard_gpt56/control/database_snapshots",
            ),
            (
                "standard_sonnet5",
                SONNET_ROOT / "control/EXTENSION_AUDIT.json",
                SONNET_ROOT / "arms/standard_sonnet5/control/database_snapshots",
            ),
            (
                "standard_opus5",
                OPUS_ROOT / "control/EXTENSION_AUDIT.json",
                OPUS_ROOT / "arms/standard_opus5/control/database_snapshots",
            ),
        ]
    )
    return sources


def main() -> None:
    cells: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for arm_id, audit_path, dump_dir in _arm_sources():
        dump_path = _latest_dump(dump_dir)
        campaigns, results = _dump_rows(dump_path)
        results_by_campaign: dict[str, list[dict[str, str]]] = defaultdict(list)
        for result in results:
            results_by_campaign[result["campaign_id"]].append(result)
        audit = _load_json(audit_path)
        audit_cells = [
            cell
            for cell in audit["cells"]
            if cell.get("arm_id", arm_id) == arm_id
        ]
        for cell in audit_cells:
            campaign_ids = list(dict.fromkeys(cell.get("campaign_ids_created", [])))
            selected_results = [
                result
                for campaign_id in campaign_ids
                for result in results_by_campaign.get(campaign_id, [])
            ]
            parameter_signatures = [
                _canonical_json(result["parameter_values_json"])
                for result in selected_results
            ]
            objective_payloads = [
                _canonical_json(result["objective_values_json"])
                for result in selected_results
            ]
            expected_objectives = EXPECTED_OBJECTIVES[cell["case"]]
            malformed = 0
            objective_mismatches = 0
            for raw, canonical in zip(
                (result["objective_values_json"] for result in selected_results),
                objective_payloads,
                strict=True,
            ):
                if canonical is None:
                    malformed += 1
                    continue
                payload = json.loads(raw)
                if set(payload) != expected_objectives or not all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in payload.values()
                ):
                    objective_mismatches += 1
            valid_parameters = [value for value in parameter_signatures if value]
            total = len(selected_results)
            unique = len(set(valid_parameters))
            duplicate_count = len(valid_parameters) - unique
            missing_campaign_ids = [
                campaign_id
                for campaign_id in campaign_ids
                if campaign_id not in campaigns
            ]
            is_no_bo = arm_id == "no_bo_gpt"
            budget_pass: bool | None = None if is_no_bo else total == 60
            cells.append(
                {
                    "arm_id": arm_id,
                    "case": cell["case"],
                    "repeat": int(cell["repeat"]),
                    "cell_id": cell["cell_id"],
                    "campaign_ids_created": campaign_ids,
                    "campaign_count_created": len(campaign_ids),
                    "campaign_result_counts": {
                        campaign_id: len(results_by_campaign.get(campaign_id, []))
                        for campaign_id in campaign_ids
                    },
                    "global_result_count": total,
                    "global_unique_parameter_count": unique,
                    "global_duplicate_parameter_count": duplicate_count,
                    "malformed_result_count": malformed,
                    "objective_mismatch_count": objective_mismatches,
                    "missing_campaign_ids": missing_campaign_ids,
                    "global_budget_pass": budget_pass,
                    "global_budget_status": (
                        "not_applicable"
                        if budget_pass is None
                        else "PASS"
                        if budget_pass
                        else "FAIL"
                    ),
                }
            )
        sources.append(
            {
                "arm_id": arm_id,
                "audit_path": str(audit_path),
                "audit_sha256": _sha256(audit_path),
                "database_dump_path": str(dump_path),
                "database_dump_sha256": _sha256(dump_path),
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "definition": {
            "budget": 60,
            "campaign_count_is_diagnostic_only": True,
            "pass": "exactly 60 attempted objective evaluations in total",
            "scientific_checks": (
                "unique parameter vectors, duplicates, malformed objective records, "
                "objective-schema mismatches, and missing owned campaigns are "
                "reported separately"
            ),
            "no_bo_mcp": "not applicable by architecture design",
        },
        "sources": sources,
        "cells": sorted(
            cells,
            key=lambda cell: (cell["arm_id"], cell["case"], cell["repeat"]),
        ),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
