#!/usr/bin/env python3
"""Overlay infrastructure-corrected cells and build the final comparison report."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


REPO = Path(__file__).resolve().parents[4]
ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "figures"
BASE = REPO / "outputs/bo_mcp_evals/claude5_standard_comparison_report_20260805T235859Z"
INFRA_REPLACEMENTS = (
    REPO / "outputs/bo_mcp_evals/infrastructure_replacements_20260807T052449Z"
)
PROMPT_REPLACEMENTS = (
    REPO / "outputs/bo_mcp_evals/prompt_clarified_replacements_20260807T174900Z"
)
TARGETED_REPLACEMENT_PATHS = {
    ("standard_gpt", "synthetic_ackley_6d", 3): REPO
    / "outputs/bo_mcp_evals/baybe_duplicate_fix_gpt54_ackley_r3_20260808T002804Z/runs/prompt_gpt/arms/standard_gpt_baybe_duplicate_fix/cells/ackley_standard_gpt_baybe_duplicate_fix_r03/eval/cases/synthetic_ackley_6d",
    ("standard_glm", "synthetic_ackley_6d", 3): REPO
    / "outputs/bo_mcp_evals/baybe_duplicate_fix_glm_ackley_r3_20260808T004854Z_retry1/runs/target/arms/standard_glm_baybe_duplicate_fix/cells/ackley_standard_glm_baybe_duplicate_fix_r03/eval/cases/synthetic_ackley_6d",
    ("standard_nemotron", "synthetic_ackley_6d", 3): REPO
    / "outputs/bo_mcp_evals/baybe_duplicate_fix_nemotron_ackley_r3_20260808T004854Z_retry1/runs/target/arms/standard_nemotron_baybe_duplicate_fix/cells/ackley_standard_nemotron_baybe_duplicate_fix_r03/eval/cases/synthetic_ackley_6d",
}
BASE_DATA = BASE / "control/REPORT_DATA.json"
BASE_COST = BASE / "control/FULL_COST_AUDIT.json"
RULES = REPO / "evals/bo_mcp/benchmark_cost_rules_2026-08-06.json"
MATRIX_TRAJECTORIES = (
    Path("/local-scratch/home/lynnfang00/research")
    / "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/full_matrix_20260730T154405Z/control/TRAJECTORY_METRICS.json"
)

IDS = [
    "standard_gpt",
    "standard_glm",
    "standard_gemini",
    "standard_deepseek",
    "standard_nemotron",
    "standard_gpt56",
    "standard_sonnet5",
    "standard_opus5",
]
LABELS = {
    "standard_gpt": "GPT-5.4",
    "standard_glm": "GLM-5.1",
    "standard_gemini": "Gemini 3.5 Flash",
    "standard_deepseek": "DeepSeek V4 Pro",
    "standard_nemotron": "Nemotron 3 Ultra",
    "standard_gpt56": "GPT-5.6",
    "standard_sonnet5": "Claude Sonnet 5",
    "standard_opus5": "Claude Opus 5",
}
COLORS = [
    "#2563eb",
    "#16a34a",
    "#9333ea",
    "#dc2626",
    "#76b900",
    "#f59e0b",
    "#d97706",
    "#111827",
]
CASES = ["synthetic_ackley_6d", "direct_arylation"]
CASE_LABELS = {
    "synthetic_ackley_6d": "Ackley 6D",
    "direct_arylation": "Direct Arylation",
}
ARCH_IDS = ["standard_gpt", "main_script_gpt", "direct_tool_gpt", "no_bo_gpt"]
ARCH_LABELS = {
    "standard_gpt": "Standard",
    "main_script_gpt": "Main-script",
    "direct_tool_gpt": "Direct-tool",
    "no_bo_gpt": "No-BO-MCP",
}

INFRA_REPLACEMENT_SPECS = (
    {
        ("standard_sonnet5", case, repeat): ("sonnet5", "standard_sonnet5_fixed_v2")
        for case in CASES
        for repeat in range(1, 4)
    }
    | {
        ("standard_opus5", case, repeat): ("opus5", "standard_opus5_fixed")
        for case in CASES
        for repeat in range(1, 4)
    }
    | {
        ("standard_gemini", case, repeat): ("gemini", "standard_gemini_fixed_v2")
        for case in CASES
        for repeat in range(1, 4)
    }
    | {
        ("standard_deepseek", "synthetic_ackley_6d", 1): (
            "deepseek",
            "standard_deepseek_fixed",
        ),
        ("standard_deepseek", "synthetic_ackley_6d", 2): (
            "deepseek_followup",
            "standard_deepseek_fixed_followup",
        ),
        ("standard_deepseek", "synthetic_ackley_6d", 3): (
            "deepseek_followup",
            "standard_deepseek_fixed_followup",
        ),
        ("standard_gpt56", "direct_arylation", 3): ("gpt56", "standard_gpt56_fixed"),
    }
)

PROMPT_STANDARD_SPECS = (
    {
        ("standard_gpt", "synthetic_ackley_6d", 3): (
            "prompt_gpt",
            "standard_gpt_prompt_v2",
        ),
        ("standard_gpt", "direct_arylation", 1): (
            "prompt_gpt",
            "standard_gpt_prompt_v2",
        ),
        ("standard_gpt", "direct_arylation", 2): (
            "prompt_gpt",
            "standard_gpt_prompt_v2",
        ),
        ("standard_gemini", "synthetic_ackley_6d", 3): (
            "prompt_gemini",
            "standard_gemini_prompt_v2",
        ),
        ("standard_gemini", "direct_arylation", 2): (
            "prompt_gemini",
            "standard_gemini_prompt_v2",
        ),
        ("standard_nemotron", "synthetic_ackley_6d", 3): (
            "prompt_nemotron",
            "standard_nemotron_prompt_v2",
        ),
        ("standard_nemotron", "direct_arylation", 1): (
            "prompt_nemotron",
            "standard_nemotron_prompt_v2",
        ),
        ("standard_opus5", "direct_arylation", 2): (
            "prompt_opus5",
            "standard_opus5_prompt_v2",
        ),
    }
    | {
        ("standard_glm", case, repeat): ("prompt_glm", "standard_glm_prompt_v2")
        for case in CASES
        for repeat in range(1, 4)
    }
    | {
        ("standard_deepseek", "synthetic_ackley_6d", repeat): (
            "prompt_deepseek",
            "standard_deepseek_prompt_v2",
        )
        for repeat in (2, 3)
    }
    | {
        ("standard_deepseek", "direct_arylation", repeat): (
            "prompt_deepseek",
            "standard_deepseek_prompt_v2",
        )
        for repeat in range(1, 4)
    }
    | {
        ("standard_sonnet5", "direct_arylation", repeat): (
            "prompt_sonnet5",
            "standard_sonnet5_prompt_v2",
        )
        for repeat in range(1, 4)
    }
)
PROMPT_ARCHITECTURE_SPECS = {
    ("main_script_gpt", "synthetic_ackley_6d", 1): (
        "prompt_main_script_gpt",
        "main_script_gpt_prompt_v2",
    )
}

# Later prompt-clarified cells supersede the same cells in the infrastructure
# cohort; all other infrastructure replacements remain selected.
REPLACEMENT_SPECS = INFRA_REPLACEMENT_SPECS | PROMPT_STANDARD_SPECS

NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_dir(root: Path, run: str, physical_arm: str, case: str, repeat: int) -> Path:
    prefix = "ackley" if case == "synthetic_ackley_6d" else "direct_arylation"
    cell = f"{prefix}_{physical_arm}_r{repeat:02d}"
    return (
        root
        / "runs"
        / run
        / "arms"
        / physical_arm
        / "cells"
        / cell
        / "eval"
        / "cases"
        / case
    )


def selected_paths() -> dict[tuple[str, str, int], Path]:
    found = {}
    missing = []
    for key, (run, physical_arm) in REPLACEMENT_SPECS.items():
        root = (
            PROMPT_REPLACEMENTS if key in PROMPT_STANDARD_SPECS else INFRA_REPLACEMENTS
        )
        path = cell_dir(root, run, physical_arm, key[1], key[2])
        if not (path / "output.json").is_file():
            missing.append(str(path / "output.json"))
        else:
            found[key] = path
    for key, path in TARGETED_REPLACEMENT_PATHS.items():
        if not (path / "output.json").is_file():
            missing.append(str(path / "output.json"))
        else:
            found[key] = path
    if missing:
        raise RuntimeError(
            "Replacement campaigns are not complete:\n" + "\n".join(missing)
        )
    return found


def selected_architecture_paths() -> dict[tuple[str, str, int], Path]:
    found = {}
    missing = []
    for key, (run, physical_arm) in PROMPT_ARCHITECTURE_SPECS.items():
        path = cell_dir(PROMPT_REPLACEMENTS, run, physical_arm, key[1], key[2])
        if not (path / "output.json").is_file():
            missing.append(str(path / "output.json"))
        else:
            found[key] = path
    if missing:
        raise RuntimeError(
            "Architecture replacements are not complete:\n" + "\n".join(missing)
        )
    return found


def bo_block(path: Path, output: dict[str, Any]) -> dict[str, Any]:
    recovered = path / "metrics_recovered.json"
    metrics_path = recovered if recovered.is_file() else path / "metrics.json"
    metrics = (
        load(metrics_path) if metrics_path.is_file() else output.get("metrics", {})
    )
    return metrics.get("bo_mcp", {}) if isinstance(metrics, dict) else {}


def scientific_pass(bo: dict[str, Any]) -> bool:
    curve = bo.get("eval_best_so_far_curve")
    return (
        bo.get("attempted_objective_evaluations") == 60
        and bo.get("completed_objective_evaluations") == 60
        and bo.get("unique_parameter_evaluations") == 60
        and bo.get("duplicate_evaluations", 0) == 0
        and bo.get("objective_schema_status") == "matched"
        and bo.get("backend_status") == "matched"
        and str(bo.get("verification_status", "")).startswith(
            ("verified", "diagnostics_failed_results_verified")
        )
        and isinstance(curve, list)
        and len(curve) == 60
    )


def local_nemotron_curve(path: Path) -> list[float]:
    artifact = path / "workspace/bo-mcp-eval/ackley_6d_results/evaluations.jsonl"
    rows = [json.loads(line) for line in artifact.read_text().splitlines() if line]
    rows.sort(key=lambda row: int(row["evaluation_index"]))
    points = {
        tuple(round(float(row["parameter_values"][f"x_{i}"]), 12) for i in range(1, 7))
        for row in rows
    }
    indices = {int(row["evaluation_index"]) for row in rows}
    if len(rows) != 60 or len(points) != 60 or indices != set(range(1, 61)):
        raise ValueError(
            "Nemotron local artifact is not a complete unique 60-point run"
        )
    curve = []
    best = -math.inf
    for row in rows:
        if row.get("status") != "success":
            raise ValueError("Nemotron local artifact contains a failed evaluation")
        best = max(best, float(row["objective_values"]["surface_response"]))
        curve.append(best)
    return curve


def replacement_run(
    key: tuple[str, str, int], path: Path
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    arm_id, case, repeat = key
    output_path = path / "output.json"
    output = load(output_path)
    bo = bo_block(path, output)
    local_only_result = key == ("standard_nemotron", "synthetic_ackley_6d", 3)
    if local_only_result:
        curve = local_nemotron_curve(path)
        bo = {
            **bo,
            "attempted_objective_evaluations": 60,
            "completed_objective_evaluations": 60,
            "unique_parameter_evaluations": 60,
            "duplicate_evaluations": 0,
            "objective_schema_status": "matched",
            "backend_status": "matched",
            "verification_status": "verified_local_artifact_plus_bo_mcp_results",
            "best_objective_value": curve[-1],
            "eval_best_so_far_curve": curve,
        }
    recovery_path = path.parents[4] / "control/READBACK_RECOVERY_AUDIT.json"
    recovery = load(recovery_path) if recovery_path.is_file() else None
    failure_audit_path = path.parents[4] / "control/FAILURE_DB_AUDIT.json"
    failure_audit = load(failure_audit_path) if failure_audit_path.is_file() else None
    if recovery:
        selected = recovery["selected_status"]
        bo = {
            **bo,
            "objective_schema_status": "matched",
            "backend_status": "matched",
            "backend_resolved": selected["backend_resolved"],
            "campaign_count_created": output.get("campaign_count_created"),
        }
    if failure_audit:
        bo = {
            **bo,
            "attempted_objective_evaluations": failure_audit[
                "attempted_objective_evaluations"
            ],
            "completed_objective_evaluations": failure_audit[
                "attempted_objective_evaluations"
            ],
            "unique_parameter_evaluations": failure_audit[
                "unique_parameter_evaluations"
            ],
            "duplicate_evaluations": failure_audit["duplicate_parameter_evaluations"],
            "campaign_count_created": failure_audit["campaign_count_created"],
            "backend_status": "matched",
            "backend_resolved": failure_audit["backend_resolved"],
            "verification_status": "database_dump_audited",
            "best_objective_value": failure_audit.get("best_objective_value"),
        }
    arch = output.get("architecture", {})
    architecture_ok = not arch.get("mode_violation_reasons", []) and (
        arm_id == "main_script_gpt"
        or int(arch.get("subagent_delegation_count", 0)) >= 1
    )
    artifact_ok = int(arch.get("script_artifact_count", 0)) >= 1
    if failure_audit:
        architecture_ok = bool(failure_audit["architecture_pass"])
        artifact_ok = bool(
            failure_audit["architecture_evidence"].get("specialist_authored_script")
        )
    science_ok = scientific_pass(bo) or bool(
        recovery and recovery["selected_status"]["scientific_pass"]
    )
    budget_ok = bo.get("attempted_objective_evaluations") == 60
    backend_values = sorted(
        {str(v) for v in (bo.get("campaign_backends_resolved") or {}).values() if v}
    )
    backend = ", ".join(backend_values) or bo.get("backend_resolved") or "unknown"
    observed_curve = bo.get("eval_best_so_far_curve")
    curve = observed_curve if science_ok else None
    auc = (
        statistics.fmean(float(v) for v in curve)
        / (100.0 if case == "direct_arylation" else 1.0)
        if curve
        else None
    )
    observed_auc = (
        statistics.fmean(float(v) for v in observed_curve[:60])
        / (100.0 if case == "direct_arylation" else 1.0)
        if isinstance(observed_curve, list) and len(observed_curve) >= 60
        else None
    )
    row = {
        "arm_id": arm_id,
        "label": LABELS[arm_id] if arm_id in LABELS else ARCH_LABELS[arm_id],
        "case": case,
        "repeat": repeat,
        "cell_id": path.parents[2].name,
        "backend": backend,
        "backend_pass": bo.get("backend_status") == "matched",
        "artifact_pass": artifact_ok,
        "scientific_status": "PASS" if science_ok else "FAIL",
        "final_quality": float(curve[-1]) if curve else None,
        "observed_best_objective": bo.get("best_objective_value"),
        "observed_normalized_auc_60": observed_auc,
        "normalized_auc_60": auc,
        "strict_status": "PASS" if output.get("success") else "FAIL",
        "architecture_contract_pass": architecture_ok,
        "global_budget_status": "PASS" if budget_ok else "FAIL",
        "global_result_count": bo.get("attempted_objective_evaluations"),
        "global_unique_parameter_count": bo.get("unique_parameter_evaluations"),
        "global_duplicate_parameter_count": bo.get("duplicate_evaluations"),
        "full_protocol_pass": bool(
            science_ok and architecture_ok and artifact_ok and budget_ok
        ),
        "campaigns": bo.get(
            "campaign_count_created", output.get("campaign_count_created")
        ),
        "campaign_result_counts": bo.get("campaign_result_counts"),
        "bo_mcp_submitted_result_count": (
            sum(
                int(value)
                for value in (bo.get("campaign_result_counts") or {}).values()
            )
            if local_only_result
            else None
        ),
        "special_case_note": (
            "PASS; 60 unique objective evaluations; one valid result remained local after an invalid BO-MCP submission payload (59 submitted)"
            if local_only_result
            else None
        ),
        "attempted_evaluations": bo.get("attempted_objective_evaluations"),
        "terminal_state": (
            "infrastructure_readback_recovered"
            if recovery
            else "completed"
            if output.get("success")
            else "failed"
        ),
        "terminal_error": output.get("error"),
        "verification_status": bo.get("verification_status"),
        "evidence_source": (
            "baybe_duplicate_fix_replacement_20260808"
            if key in TARGETED_REPLACEMENT_PATHS
            else "prompt_clarified_replacement_20260807"
            if PROMPT_REPLACEMENTS in path.parents
            else "infrastructure_replacement_20260807"
        ),
        "source_output_path": str(output_path),
        "source_output_sha256": digest(output_path),
        "runtime_s": float(output.get("total_runtime_s") or 0.0),
        "cost_status": output.get("cost_breakdown", {})
        .get("combined", {})
        .get("cost_status", "unavailable"),
        "cost_usd": output.get("cost_breakdown", {})
        .get("combined", {})
        .get("cost_usd"),
    }
    trajectory = None
    if curve:
        trajectory = {
            "arm_id": arm_id,
            "case": case,
            "repeat": repeat,
            "cell_id": row["cell_id"],
            "best_at_60": row["final_quality"],
            "best_so_far": [float(v) for v in curve],
            "auc": {"60": auc},
            "scientific_pass": True,
            "protocol_pass": row["full_protocol_pass"],
            "source_path": str(path / "metrics.json"),
        }
    return row, trajectory


def new_cost_cell(key: tuple[str, str, int], path: Path) -> dict[str, Any]:
    arm_id, case, repeat = key
    output_path = path / "output.json"
    output = load(output_path)
    records = [
        json.loads(line)
        for line in (path / "provider_requests.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    starts = [r for r in records if r.get("event") == "model_request_started"]
    responses = [r for r in records if r.get("event") == "model_response"]
    seen: set[str] = set()
    duplicates = 0
    models: dict[str, dict[str, Any]] = {}
    rules = load(RULES)["models"]
    for record in responses:
        rid = record.get("provider_response_id")
        if rid and rid in seen:
            duplicates += 1
            continue
        if rid:
            seen.add(rid)
        response = record.get("response") or {}
        model = (
            response.get("model_name")
            or record.get("model_name")
            or record.get("actual_model")
            or "unknown"
        )
        usage = response.get("usage") or record.get("usage") or {}
        entry = models.setdefault(
            model,
            {
                "provider": (
                    response.get("provider_name")
                    or record.get("provider_name")
                    or record.get("provider")
                ),
                "responses": 0,
                "responses_with_usage": 0,
                "tokens": {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0},
                "known_list_cost_usd": 0.0,
            },
        )
        entry["responses"] += 1
        if usage:
            entry["responses_with_usage"] += 1
        cache_read = int(usage.get("cache_read_tokens") or 0)
        cache_write = int(usage.get("cache_write_tokens") or 0)
        total_input = int(usage.get("input_tokens") or 0)
        explicit_uncached = int((usage.get("details") or {}).get("input_tokens") or 0)
        uncached_input = (
            explicit_uncached
            if explicit_uncached
            else max(0, total_input - cache_read - cache_write)
        )
        entry["tokens"]["input"] += uncached_input
        entry["tokens"]["cache_read"] += cache_read
        entry["tokens"]["cache_write"] += cache_write
        entry["tokens"]["output"] += int(usage.get("output_tokens") or 0)
        details = (
            response.get("provider_details") or record.get("provider_details") or {}
        )
        upstream = details.get("upstream_inference_cost")
        if isinstance(upstream, (int, float)):
            entry["known_list_cost_usd"] += float(upstream)
        else:
            rule = rules.get(model, {})
            if rule.get("pricing_method") == "frozen_public_token_rates" and usage:
                entry["known_list_cost_usd"] += (
                    uncached_input * float(rule["input"])
                    + cache_write * float(rule["cache_write"])
                    + cache_read * float(rule["cache_read"])
                    + int(usage.get("output_tokens") or 0) * float(rule["output"])
                ) / 1_000_000
    combined = output.get("cost_breakdown", {}).get("combined", {})
    ledger = output.get("request_ledger", {})
    for entry in models.values():
        entry["priced_responses"] = (
            entry["responses"]
            if combined.get("pricing_unavailable_response_count", 0) == 0
            else 0
        )
        entry["unpriced_responses"] = entry["responses"] - entry["priced_responses"]
    # The cell total comes from the same authoritative calculator used at run time.
    known = float(combined.get("cost_usd") or 0.0)
    status = combined.get("cost_status", "unavailable")
    return {
        "cohort": (
            "baybe_duplicate_fix_20260808"
            if key in TARGETED_REPLACEMENT_PATHS
            else "prompt_clarified_20260807"
            if PROMPT_REPLACEMENTS in path.parents
            else "infrastructure_corrected_20260807"
        ),
        "arm_id": arm_id,
        "cell_id": path.parents[2].name,
        "case": case,
        "repeat": repeat,
        "output_path": str(output_path),
        "output_sha256": digest(output_path),
        "transport_trace": {"total_llm_posts": len(starts)},
        "observed_response_records": len(responses),
        "captured_unique_responses": len(responses) - duplicates,
        "duplicate_response_records": duplicates,
        "response_records_without_id": sum(
            not r.get("provider_response_id") for r in responses
        ),
        "conflicting_duplicate_records": 0,
        "unmatched_traced_provider_calls": len(
            ledger.get("billing_unresolved_request_ids", [])
        )
        + len(ledger.get("unterminated_model_request_ids", [])),
        "captured_responses_without_trace": max(0, len(responses) - len(starts)),
        "responses_without_usage": sum(
            not (r.get("response") or {}).get("usage") for r in responses
        ),
        "models": models,
        "known_list_cost_usd": known,
        "token_status": "exact" if ledger.get("usage_complete") else "lower_bound",
        "cost_status": status,
        "unpriced_response_count": int(combined.get("unpriced_response_count", 0)),
        "unpriced_reasons": {reason: 1 for reason in combined.get("cost_errors", [])},
        "failed_task_count": sum(
            1 for r in records if r.get("event") == "model_request_error"
        ),
    }


def summarize_cost(cells: list[dict[str, Any]]) -> dict[str, Any]:
    result = {
        "cells": len(cells),
        "cost_status_counts": dict(Counter(c["cost_status"] for c in cells)),
        "traced_provider_calls": sum(
            c["transport_trace"]["total_llm_posts"] for c in cells
        ),
        "captured_unique_responses": sum(c["captured_unique_responses"] for c in cells),
        "duplicate_response_records": sum(
            c["duplicate_response_records"] for c in cells
        ),
        "unmatched_traced_provider_calls": sum(
            c["unmatched_traced_provider_calls"] for c in cells
        ),
        "failed_task_count": sum(c.get("failed_task_count", 0) for c in cells),
        "known_list_cost_usd": sum(
            float(c.get("known_list_cost_usd") or 0) for c in cells
        ),
    }
    statuses = set(result["cost_status_counts"])
    result["cost_status"] = (
        "unavailable"
        if "unavailable" in statuses
        else "lower_bound"
        if "lower_bound" in statuses
        else "exact_calculated"
    )
    return result


def apply_nemotron_free_endpoint(cells: list[dict[str, Any]]) -> None:
    """Price the benchmarked NVIDIA developer endpoint at its public $0 charge."""
    for cell in cells:
        if cell["arm_id"] != "standard_nemotron":
            continue
        models = cell["models"]
        specialist = models.setdefault(
            NEMOTRON_MODEL,
            {
                "provider": "nvidia",
                "responses": 0,
                "responses_with_usage": 0,
                "tokens": {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0},
            },
        )
        specialist.update(
            {
                "known_list_cost_usd": 0.0,
                "priced_responses": specialist.get("responses", 0),
                "unpriced_responses": 0,
                "pricing_methods": ["free_provider_endpoint"],
            }
        )
        traced_free = int(cell["transport_trace"].get("nvidia_chat_completions", 0))
        missing_free = max(0, traced_free - int(specialist.get("responses", 0)))
        missing_paid = max(
            0, int(cell.get("unmatched_traced_provider_calls", 0)) - missing_free
        )
        cell["free_endpoint_cost_usd"] = 0.0
        cell["free_endpoint_unmatched_calls"] = missing_free
        cell["unmatched_traced_provider_calls"] = missing_paid
        cell["cost_status"] = "exact_calculated" if missing_paid == 0 else "lower_bound"
        cell["unpriced_reasons"] = (
            {} if missing_paid == 0 else {"missing_paid_gpt_5_4_usage": missing_paid}
        )


def safe_sd(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else None


def arm_case_summary(
    trajectories: list[dict[str, Any]], arm_id: str, case: str
) -> dict[str, Any]:
    selected = [t for t in trajectories if t["arm_id"] == arm_id and t["case"] == case]
    finals = [float(t["best_at_60"]) for t in selected]
    aucs = [float(t["auc"]["60"]) for t in selected]
    return {
        "requested_runs": 3,
        "scientifically_complete_runs": len(selected),
        "mean_final_quality": statistics.fmean(finals) if finals else None,
        "sample_sd_final_quality": safe_sd(finals),
        "mean_normalized_auc_60": statistics.fmean(aucs) if aucs else None,
        "sample_sd_normalized_auc_60": safe_sd(aucs),
    }


def aggregate_arm(
    arm: dict[str, Any],
    rows: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    cost_cells: list[dict[str, Any]],
) -> None:
    arm_id = arm["arm_id"]
    selected_rows = [r for r in rows if r["arm_id"] == arm_id]
    cells = [c for c in cost_cells if c["arm_id"] == arm_id]
    summary = summarize_cost(cells)
    arm["label"] = LABELS[arm_id]
    arm["cases"] = {
        case: arm_case_summary(trajectories, arm_id, case) for case in CASES
    }
    arm["reliability"] = {
        "attempts": 6,
        "scientifically_complete": sum(
            r["scientific_status"] == "PASS" for r in selected_rows
        ),
        "architecture_contract_passes": sum(
            r.get("architecture_contract_pass") is True for r in selected_rows
        ),
        "global_budget_passes": sum(
            r.get("global_budget_status") == "PASS" for r in selected_rows
        ),
        "full_protocol_passes": sum(
            r.get("full_protocol_pass") is True for r in selected_rows
        ),
        "total_campaigns": sum(int(r.get("campaigns") or 0) for r in selected_rows),
    }
    total_tokens = sum(
        sum(int(v) for v in model["tokens"].values())
        for c in cells
        for model in c["models"].values()
    )
    resource = {
        "runtime_s": sum(float(r.get("runtime_s") or 0) for r in selected_rows),
        "requests": summary["traced_provider_calls"],
        "total_tokens": total_tokens,
        "cost_status": summary["cost_status"],
        "known_list_cost_usd": summary["known_list_cost_usd"],
        "exact_calculated_cells": summary["cost_status_counts"].get(
            "exact_calculated", 0
        ),
        "lower_bound_cells": summary["cost_status_counts"].get("lower_bound", 0),
        "unavailable_cells": summary["cost_status_counts"].get("unavailable", 0),
        "unmatched_provider_calls": summary["unmatched_traced_provider_calls"],
        "duplicate_response_records_removed": summary["duplicate_response_records"],
    }
    if summary["cost_status"] == "exact_calculated":
        resource["cost_usd"] = summary["known_list_cost_usd"]
    elif summary["cost_status"] == "lower_bound":
        resource["known_cost_usd_lower_bound"] = summary["known_list_cost_usd"]
    else:
        resource["known_priced_cost_usd"] = summary["known_list_cost_usd"]
    arm["resources"] = resource


def patch_old_runtime(rows: list[dict[str, Any]], old_cost: dict[str, Any]) -> None:
    cost_map = {
        (c["arm_id"], c["case"], int(c["repeat"])): c for c in old_cost["cells"]
    }
    for row in rows:
        if "runtime_s" in row:
            continue
        cell = cost_map[(row["arm_id"], row["case"], int(row["repeat"]))]
        output = load(Path(cell["output_path"]))
        row["runtime_s"] = float(output.get("total_runtime_s") or 0.0)
        row["cost_status"] = cell["cost_status"]
        row["cost_usd"] = float(cell.get("known_list_cost_usd") or 0.0)


def save(fig: plt.Figure, stem: str) -> None:
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    for suffix in ("png", "svg"):
        fig.savefig(FIGURES / f"{stem}.{suffix}", dpi=210, bbox_inches="tight")
    plt.close(fig)


def observed_result(row: dict[str, Any]) -> float | None:
    for key in ("observed_best_objective", "observed_final_quality", "final_quality"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return None


def all_observed_plot(rows: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    offsets = {1: -0.18, 2: 0.0, 3: 0.18}
    for ax, case in zip(axes, CASES, strict=True):
        case_rows = [row for row in rows if row["case"] == case]
        for index, (arm, color) in enumerate(zip(IDS, COLORS, strict=True)):
            for row in [item for item in case_rows if item["arm_id"] == arm]:
                value = observed_result(row)
                x = index + offsets[int(row["repeat"])]
                if value is None:
                    ax.scatter(x, 0, marker="x", color=color, s=55, linewidth=2)
                    ax.annotate(
                        "no result",
                        (x, 0),
                        xytext=(0, 7),
                        textcoords="offset points",
                        ha="center",
                        fontsize=7,
                    )
                    continue
                passed = row.get("full_protocol_pass") is True
                ax.scatter(
                    x,
                    value,
                    marker="o" if passed else "X",
                    color=color,
                    edgecolor="black",
                    linewidth=0.6,
                    s=58 if passed else 68,
                    zorder=3,
                )
                if not passed:
                    total = row.get("global_result_count")
                    unique = row.get("global_unique_parameter_count")
                    ax.annotate(
                        f"{total}/{unique}",
                        (x, value),
                        xytext=(0, 5 + 7 * (int(row["repeat"]) - 1)),
                        textcoords="offset points",
                        ha="center",
                        fontsize=7,
                    )
        ax.set_title(CASE_LABELS[case])
        ax.set_xticks(
            np.arange(len(IDS)), [LABELS[arm] for arm in IDS], rotation=28, ha="right"
        )
        ax.set_ylabel("Observed best objective")
        ax.set_ylim((-0.05, 1.12) if case == CASES[0] else (-5, 112))
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(
        handles=[
            Line2D(
                [0], [0], marker="o", linestyle="", color="black", label="Protocol PASS"
            ),
            Line2D(
                [0],
                [0],
                marker="X",
                linestyle="",
                color="black",
                label="FAIL (label = total/unique)",
            ),
            Line2D(
                [0],
                [0],
                marker="x",
                linestyle="",
                color="black",
                label="No usable result",
            ),
        ],
        fontsize=8,
        loc="lower left",
    )
    fig.suptitle(
        "All observed run outcomes (descriptive; failed cells may use unequal evaluation budgets)"
    )
    save(fig, "standard_all_observed_results")


def quality_plot(trajectories: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    specs = [
        (CASES[0], "best_at_60", "Ackley final quality", 1.0),
        (CASES[0], "auc", "Ackley normalized AUC@60", 1.0),
        (CASES[1], "best_at_60", "Direct Arylation final yield (%)", 105.0),
        (CASES[1], "auc", "Direct Arylation normalized AUC@60", 1.0),
    ]
    x = np.arange(len(IDS))
    for ax, (case, metric, title, ceiling) in zip(axes.flat, specs, strict=True):
        values = []
        for arm in IDS:
            ts = [t for t in trajectories if t["arm_id"] == arm and t["case"] == case]
            values.append(
                [float(t["auc"]["60"] if metric == "auc" else t[metric]) for t in ts]
            )
        means = [statistics.fmean(v) if v else math.nan for v in values]
        errors = [statistics.stdev(v) if len(v) > 1 else 0.0 for v in values]
        ax.bar(x, means, yerr=errors, capsize=4, color=COLORS, alpha=0.86)
        for i, vals in enumerate(values):
            offsets = (
                np.linspace(-0.11, 0.11, len(vals))
                if len(vals) > 1
                else np.asarray([0.0])
            )
            ax.scatter(i + offsets, vals, color="black", s=20, zorder=3)
        ax.set_title(title)
        ax.set_xticks(x, [LABELS[a] for a in IDS], rotation=28, ha="right")
        ax.set_ylim(0, ceiling)
        ax.grid(axis="y", alpha=0.25)
        for i, vals in enumerate(values):
            if not vals:
                ax.text(
                    i,
                    ceiling * 0.48,
                    "no valid\nrepeat",
                    ha="center",
                    va="center",
                    fontsize=8,
                )
    fig.suptitle(
        "Standard architecture: quality across specialist models (mean ± sample SD; dots are repeats)"
    )
    save(fig, "standard_quality_auc_final")


def convergence_plot(trajectories: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    for ax, case in zip(axes, CASES, strict=True):
        for arm, color in zip(IDS, COLORS, strict=True):
            curves = [
                t["best_so_far"]
                for t in trajectories
                if t["arm_id"] == arm and t["case"] == case
            ]
            if not curves:
                continue
            arr = np.asarray(curves, dtype=float)
            mean = arr.mean(axis=0)
            x = np.arange(1, 61)
            ax.plot(x, mean, label=LABELS[arm], color=color, linewidth=2)
            if len(curves) > 1:
                sd = arr.std(axis=0, ddof=1)
                ax.fill_between(x, mean - sd, mean + sd, color=color, alpha=0.12)
        ax.set_title(CASE_LABELS[case])
        ax.set_xlabel("Objective evaluation")
        ax.set_ylabel("Best-so-far quality")
        ax.grid(alpha=0.25)
    axes[1].legend(fontsize=8, loc="lower right")
    fig.suptitle("Standard architecture convergence (mean ± sample SD)")
    save(fig, "standard_convergence_final")


def resource_plot(arms: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    x = np.arange(len(arms))
    labels = [a["label"] for a in arms]
    specs = [
        ("Workflow cost (USD)", [a["resources"]["known_list_cost_usd"] for a in arms]),
        ("Runtime (hours)", [a["resources"]["runtime_s"] / 3600 for a in arms]),
        (
            "Structured tokens (millions)",
            [a["resources"]["total_tokens"] / 1e6 for a in arms],
        ),
        ("Provider requests", [a["resources"]["requests"] for a in arms]),
    ]
    for ax, (title, vals) in zip(axes.flat, specs, strict=True):
        bars = ax.bar(x, vals, color=COLORS, alpha=0.86)
        for i, (bar, arm) in enumerate(zip(bars, arms, strict=True)):
            if (
                arm["resources"]["cost_status"] != "exact_calculated"
                and title == "Workflow cost (USD)"
            ):
                bar.set_hatch("///")
            ax.text(
                i,
                float(vals[i]) + max(vals or [1]) * 0.015,
                f"{vals[i]:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=20,
            )
        ax.set_title(title)
        ax.set_xticks(x, labels, rotation=28, ha="right")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle(
        "Standard workflow resources (total includes GPT-5.4 main agent; Nemotron specialist $0)"
    )
    save(fig, "standard_resources_final")


def architecture_resource_plot(aggregates: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    x = np.arange(len(aggregates))
    labels = [ARCH_LABELS[item["architecture"]] for item in aggregates]
    specs = [
        ("Workflow cost (USD)", [item["total_cost_usd"] for item in aggregates]),
        ("Runtime (hours)", [item["runtime_s"] / 3600 for item in aggregates]),
        (
            "Structured tokens (millions)",
            [item["total_tokens"] / 1e6 for item in aggregates],
        ),
        ("Provider requests", [item["requests"] for item in aggregates]),
    ]
    for ax, (title, values) in zip(axes.flat, specs, strict=True):
        bars = ax.bar(x, values, color=COLORS[: len(aggregates)], alpha=0.86)
        for index, (bar, aggregate) in enumerate(zip(bars, aggregates, strict=True)):
            if (
                title == "Workflow cost (USD)"
                and aggregate["cost_status"] != "exact_calculated"
            ):
                bar.set_hatch("///")
            ax.text(
                index,
                float(values[index]) + max(values or [1]) * 0.015,
                f"{values[index]:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        ax.set_title(title)
        ax.set_xticks(x, labels, rotation=20, ha="right")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("GPT-5.4 architecture resource comparison")
    save(fig, "architecture_resources")


def architecture_quality_plot(runs: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    specs = [
        (CASES[0], "final_quality", "Ackley final quality", 1.0),
        (CASES[0], "normalized_auc_60", "Ackley normalized AUC@60", 1.0),
        (CASES[1], "final_quality", "Direct Arylation final yield (%)", 105.0),
        (
            CASES[1],
            "normalized_auc_60",
            "Direct Arylation normalized AUC@60",
            1.0,
        ),
    ]
    x = np.arange(len(ARCH_IDS))
    colors = COLORS[: len(ARCH_IDS)]
    for ax, (case, metric, title, ceiling) in zip(axes.flat, specs, strict=True):
        values = [
            [
                float(row[metric])
                for row in runs
                if row["arm_id"] == arm
                and row["case"] == case
                and row.get("scientific_status") == "PASS"
            ]
            for arm in ARCH_IDS
        ]
        means = [statistics.fmean(vals) if vals else math.nan for vals in values]
        errors = [statistics.stdev(vals) if len(vals) > 1 else 0.0 for vals in values]
        ax.bar(x, means, yerr=errors, capsize=4, color=colors, alpha=0.86)
        for index, vals in enumerate(values):
            offsets = (
                np.linspace(-0.11, 0.11, len(vals))
                if len(vals) > 1
                else np.asarray([0.0])
            )
            ax.scatter(index + offsets, vals, color="black", s=22, zorder=3)
        ax.set_title(title)
        ax.set_xticks(
            x, [ARCH_LABELS[arm] for arm in ARCH_IDS], rotation=20, ha="right"
        )
        ax.set_ylim(0, ceiling)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle(
        "GPT-5.4 architecture quality (globally valid 60-evaluation repeats only; mean ± sample SD)"
    )
    save(fig, "architecture_quality_auc")


def architecture_convergence_plot(trajectories: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    for ax, case in zip(axes, CASES, strict=True):
        for arm, color in zip(ARCH_IDS, COLORS, strict=False):
            curves = [
                row["best_so_far"]
                for row in trajectories
                if row["arm_id"] == arm and row["case"] == case
            ]
            array = np.asarray(curves, dtype=float)
            mean = array.mean(axis=0)
            x = np.arange(1, 61)
            ax.plot(x, mean, color=color, linewidth=2, label=ARCH_LABELS[arm])
            if len(curves) > 1:
                sd = array.std(axis=0, ddof=1)
                ax.fill_between(x, mean - sd, mean + sd, color=color, alpha=0.14)
        ax.set_title(CASE_LABELS[case])
        ax.set_xlabel("Objective evaluation")
        ax.set_ylabel("Best-so-far quality")
        ax.grid(alpha=0.25)
    axes[1].legend(fontsize=9, loc="lower right")
    fig.suptitle("GPT-5.4 architecture convergence (mean ± sample SD)")
    save(fig, "architecture_convergence_final")


def architecture_auc_horizons_plot(trajectories: list[dict[str, Any]]) -> None:
    horizons = [10, 20, 30, 60]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, case in zip(axes, CASES, strict=True):
        scale = 100.0 if case == "direct_arylation" else 1.0
        for arm, color in zip(ARCH_IDS, COLORS, strict=False):
            curves = [
                row["best_so_far"]
                for row in trajectories
                if row["arm_id"] == arm and row["case"] == case
            ]
            values = [
                statistics.fmean(
                    statistics.fmean(float(value) for value in curve[:horizon]) / scale
                    for curve in curves
                )
                for horizon in horizons
            ]
            ax.plot(
                horizons,
                values,
                marker="o",
                linewidth=2,
                color=color,
                label=ARCH_LABELS[arm],
            )
        ax.set_title(CASE_LABELS[case])
        ax.set_xlabel("Evaluation horizon")
        ax.set_ylabel("Normalized best-so-far AUC")
        ax.set_xticks(horizons)
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.25)
    axes[1].legend(fontsize=9, loc="lower right")
    fig.suptitle("GPT-5.4 architecture sample efficiency by evaluation horizon")
    save(fig, "architecture_auc_horizons_final")


def architecture_reliability_plot(runs: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    x = np.arange(len(ARCH_IDS))
    width = 0.24
    science = [
        sum(row["scientific_status"] == "PASS" for row in runs if row["arm_id"] == arm)
        for arm in ARCH_IDS
    ]
    ownership = [
        sum(
            row.get("architecture_contract_pass") is True
            for row in runs
            if row["arm_id"] == arm
        )
        for arm in ARCH_IDS
    ]
    protocol = [
        sum(
            row.get("full_protocol_pass") is True
            for row in runs
            if row["arm_id"] == arm
        )
        for arm in ARCH_IDS
    ]
    axes[0].bar(x - width, science, width, label="Scientific")
    axes[0].bar(x, ownership, width, label="Architecture")
    axes[0].bar(x + width, protocol, width, label="Protocol")
    axes[0].set_ylim(0, 6.5)
    axes[0].set_ylabel("Passing runs out of 6")
    axes[0].legend(fontsize=9)
    axes[0].grid(axis="y", alpha=0.25)
    campaigns = [
        [int(row.get("campaigns") or 0) for row in runs if row["arm_id"] == arm]
        for arm in ARCH_IDS
    ]
    axes[1].bar(x, [sum(values) for values in campaigns], color=COLORS[:4])
    for index, values in enumerate(campaigns):
        offsets = np.linspace(-0.12, 0.12, len(values))
        axes[1].scatter(index + offsets, values, color="black", s=20, zorder=3)
    axes[1].set_ylabel("Campaigns (bars total; dots per run)")
    axes[1].grid(axis="y", alpha=0.25)
    for ax in axes:
        ax.set_xticks(
            x, [ARCH_LABELS[arm] for arm in ARCH_IDS], rotation=20, ha="right"
        )
    fig.suptitle("GPT-5.4 architecture reliability and campaign behavior")
    save(fig, "architecture_reliability_campaigns_final")


def architecture_efficiency_plot(aggregates: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, quality_key, title in (
        (axes[0], "ackley_auc_60", "Ackley 6D"),
        (axes[1], "direct_auc_60", "Direct Arylation"),
    ):
        for index, row in enumerate(aggregates):
            ax.scatter(
                row["total_cost_usd"],
                row[quality_key],
                s=75 + 55 * row["runtime_s"] / 3600,
                color=COLORS[index],
                edgecolor="black",
                linewidth=0.6,
            )
            ax.annotate(
                ARCH_LABELS[row["architecture"]],
                (row["total_cost_usd"], row[quality_key]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=9,
            )
        ax.set_title(title)
        ax.set_xlabel("Total workflow list cost (USD)")
        ax.set_ylabel("Normalized AUC@60")
        ax.grid(alpha=0.25)
    fig.suptitle("GPT-5.4 architecture cost–quality comparison (marker size = runtime)")
    save(fig, "architecture_cost_quality_final")


def reliability_plot(arms: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    x = np.arange(len(arms))
    width = 0.35
    science = [a["reliability"]["scientifically_complete"] for a in arms]
    protocol = [a["reliability"]["full_protocol_passes"] for a in arms]
    axes[0].bar(x - width / 2, science, width, label="Scientific PASS", color="#2563eb")
    axes[0].bar(x + width / 2, protocol, width, label="Protocol PASS", color="#16a34a")
    axes[0].set_ylim(0, 6.5)
    axes[0].set_ylabel("Runs out of 6")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(x, [a["reliability"]["total_campaigns"] for a in arms], color=COLORS)
    axes[1].set_ylabel("Campaigns (diagnostic only)")
    axes[1].grid(axis="y", alpha=0.25)
    for ax in axes:
        ax.set_xticks(x, [a["label"] for a in arms], rotation=28, ha="right")
    fig.suptitle("Reliability and campaign behavior")
    save(fig, "standard_reliability_final")


def fmt(value: Any, digits: int = 3) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def special_case(row: dict[str, Any]) -> str:
    if row.get("special_case_note"):
        return str(row["special_case_note"])
    if row.get("full_protocol_pass") is True:
        result_counts = row.get("campaign_result_counts") or {}
        nonempty = [int(count) for count in result_counts.values() if int(count) > 0]
        if len(nonempty) > 1:
            return "PASS; data split across campaigns " + "+".join(
                str(count) for count in nonempty
            )
        return "PASS"
    notes = []
    total = row.get("global_result_count")
    unique = row.get("global_unique_parameter_count")
    duplicates = row.get("global_duplicate_parameter_count") or 0
    if total != 60:
        notes.append(f"budget {total}")
    if unique != total or row.get("global_duplicate_parameter_count") not in (None, 0):
        notes.append(f"unique {unique}")
    if duplicates:
        notes.append(f"duplicates {duplicates}")
    if row.get("architecture_contract_pass") is not True:
        notes.append("architecture")
    if row.get("backend_pass") is False:
        notes.append("backend")
    terminal = str(row.get("terminal_state") or "")
    if "timeout" in terminal or "Timeout" in str(row.get("terminal_error") or ""):
        notes.append("timeout")
    return "FAIL: " + "; ".join(notes or ["protocol"])


def aggregate_table(arms: list[dict[str, Any]]) -> str:
    lines = [
        "| Specialist | Ackley final | Ackley AUC | Direct final | Direct AUC | Scientific | Protocol | Workflow cost | Time (h) | Tokens (M) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in arms:
        a, d, r = arm["cases"][CASES[0]], arm["cases"][CASES[1]], arm["resources"]
        cost = f"${r['known_list_cost_usd']:.2f}" + (
            " exact"
            if r["cost_status"] == "exact_calculated"
            else " " + r["cost_status"].replace("_", " ")
        )
        lines.append(
            f"| {arm['label']} | {fmt(a['mean_final_quality'])} | {fmt(a['mean_normalized_auc_60'])} | {fmt(d['mean_final_quality'], 2)} | {fmt(d['mean_normalized_auc_60'])} | {arm['reliability']['scientifically_complete']}/6 | {arm['reliability']['full_protocol_passes']}/6 | {cost} | {r['runtime_s'] / 3600:.2f} | {r['total_tokens'] / 1e6:.2f} |"
        )
    return "\n".join(lines)


def run_table(rows: list[dict[str, Any]], case: str) -> str:
    lines = [
        "| Model | Rep | Observed best | AUC@60 | Eval/unique | Campaigns | Architecture | Status / special case | Source | Cost | Time (s) |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---:|---:|",
    ]
    for row in [r for r in rows if r["case"] == case]:
        cost = (
            "N/A"
            if row.get("cost_usd") is None
            else f"${row['cost_usd']:.3f}"
            + ("" if row.get("cost_status") == "exact_calculated" else "†")
        )
        final = fmt(observed_result(row))
        comparable_auc = row.get("normalized_auc_60")
        descriptive_auc = row.get("observed_normalized_auc_60")
        auc = fmt(comparable_auc)
        if comparable_auc is None and descriptive_auc is not None:
            auc = f"{fmt(descriptive_auc)}‡"
        source = {
            "baybe_duplicate_fix_replacement_20260808": "BayBE duplicate-fix replacement",
            "prompt_clarified_replacement_20260807": "prompt-clarified replacement",
            "infrastructure_replacement_20260807": "infrastructure replacement",
        }.get(row.get("evidence_source"), "earlier matrix")
        lines.append(
            f"| {row['label']} | {row['repeat']} | {final} | {auc} | {row.get('global_result_count')}/{row.get('global_unique_parameter_count')} | {row.get('campaigns')} | {'PASS' if row.get('architecture_contract_pass') else 'FAIL'} | {special_case(row)} | {source} | {cost} | {row.get('runtime_s', 0):.1f} |"
        )
    return "\n".join(lines)


def failure_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Model | Case | Rep | Failure classification | Evidence |",
        "|---|---|---:|---|---|",
    ]
    for row in rows:
        if row.get("full_protocol_pass") is True:
            continue
        reasons = []
        if row.get("scientific_status") != "PASS":
            reasons.append("scientific")
        if row.get("global_budget_status") != "PASS":
            reasons.append("global-budget")
        if row.get("architecture_contract_pass") is not True:
            reasons.append("architecture")
        if row.get("backend_pass") is not True:
            reasons.append("backend")
        evidence = (
            row.get("architecture_failure_reason")
            or row.get("terminal_error")
            or (
                f"results={row.get('global_result_count')}, unique={row.get('global_unique_parameter_count')}, "
                f"duplicates={row.get('global_duplicate_parameter_count')}, campaigns={row.get('campaigns')}"
            )
        )
        lines.append(
            f"| {row['label']} | {CASE_LABELS[row['case']]} | {row['repeat']} | {', '.join(reasons) or 'protocol'} | {evidence} |"
        )
    return "\n".join(lines)


def cost_table(cost_cells: list[dict[str, Any]]) -> str:
    lines = [
        "| Arm | Case | Rep | Status | Workflow cost | Calls | Missing/unresolved paid calls | Duplicates removed | Reason |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for cell in sorted(cost_cells, key=lambda c: (c["arm_id"], c["case"], c["repeat"])):
        if cell["arm_id"] == "standard_nemotron":
            reason = (
                "GPT-5.4 list cost + Nemotron free endpoint ($0)"
                if cell["cost_status"] == "exact_calculated"
                else "Nemotron free endpoint ($0); paid GPT-5.4 usage is incomplete"
            )
        else:
            reason = (
                "complete ledger and frozen price"
                if cell["cost_status"] == "exact_calculated"
                else "; ".join(cell.get("unpriced_reasons", {}))
                or "usage or authoritative price unavailable"
            )
        lines.append(
            f"| {LABELS.get(cell['arm_id'], ARCH_LABELS.get(cell['arm_id'], cell['arm_id']))} | {CASE_LABELS[cell['case']]} | {cell['repeat']} | {cell['cost_status']} | ${float(cell.get('known_list_cost_usd') or 0):.4f} | {cell['transport_trace']['total_llm_posts']} | {cell['unmatched_traced_provider_calls']} | {cell['duplicate_response_records']} | {reason} |"
        )
    return "\n".join(lines)


def architecture_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Architecture | Ackley final/AUC | Direct final/AUC | Science | Protocol | Cost | Time (h) | Tokens (M) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {ARCH_LABELS[row['architecture']]} | {fmt(row.get('ackley_final'))}/{fmt(row.get('ackley_auc_60'))} | {fmt(row.get('direct_final'), 2)}/{fmt(row.get('direct_auc_60'))} | {row['scientific']}/6 | {row['protocol_passes']}/6 | ${row['total_cost_usd']:.2f} | {row['runtime_s'] / 3600:.2f} | {row['total_tokens'] / 1e6:.2f} |"
        )
    return "\n".join(lines)


def architecture_run_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Architecture | Case | Rep | Observed best | AUC@60 | Eval/unique | Campaigns | Architecture | Status / special case |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    ordered = sorted(
        rows,
        key=lambda row: (
            row["case"],
            ARCH_IDS.index(row["arm_id"]),
            row["repeat"],
        ),
    )
    for row in ordered:
        final = fmt(observed_result(row))
        auc = fmt(row.get("normalized_auc_60"))
        if (
            row.get("normalized_auc_60") is None
            and row.get("observed_normalized_auc_60") is not None
        ):
            auc = f"{fmt(row['observed_normalized_auc_60'])}‡"
        lines.append(
            f"| {ARCH_LABELS[row['arm_id']]} | {CASE_LABELS[row['case']]} | {row['repeat']} | {final} | {auc} | {row.get('global_result_count')}/{row.get('global_unique_parameter_count')} | {row.get('campaigns')} | {'PASS' if row.get('architecture_contract_pass') else 'FAIL'} | {special_case(row)} |"
        )
    return "\n".join(lines)


def report(
    generated: str,
    arms: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    arch_rows: list[dict[str, Any]],
    arch_runs: list[dict[str, Any]],
    cost_cells: list[dict[str, Any]],
    replacements: dict[tuple[str, str, int], Path],
) -> str:
    exact = sum(c["cost_status"] == "exact_calculated" for c in cost_cells)
    lower = sum(c["cost_status"] == "lower_bound" for c in cost_cells)
    unavailable = sum(c["cost_status"] == "unavailable" for c in cost_cells)
    budget_failed_rows = [
        row for row in rows if row.get("global_budget_status") != "PASS"
    ]
    prompt_budget_failures = sum(
        row.get("evidence_source") == "prompt_clarified_replacement_20260807"
        for row in budget_failed_rows
    )
    infrastructure_budget_failures = sum(
        row.get("evidence_source") == "infrastructure_replacement_20260807"
        for row in budget_failed_rows
    )
    earlier_budget_failures = (
        len(budget_failed_rows)
        - prompt_budget_failures
        - infrastructure_budget_failures
    )
    over_budget = sum(
        (row.get("global_result_count") or 0) > 60 for row in budget_failed_rows
    )
    under_budget = sum(
        (row.get("global_result_count") or 0) < 60 for row in budget_failed_rows
    )
    return f"""# Full framework comparison: verified final report

Generated: `{generated}`

## Scope and interpretation

This report covers both benchmark cases (Ackley 6D and Direct Arylation), all eight specialist models under the Standard architecture, and GPT-5.4 under four architectures. Each requested cell has a budget of exactly 60 objective evaluations and three repeats per case. A model or agent failure is retained as an outcome; a replacement is used only where benchmark infrastructure—not model behavior—was defective.

Every run's observed best result is shown, including failed, over-budget, under-budget, duplicate, timeout, and architecture-invalid runs. `Budget PASS` means exactly 60 attempted objective evaluations in total. `Scientific PASS` additionally requires completed, unique benchmark-objective evaluations with the expected objective schema and backend and a complete result-derived trajectory. `Architecture PASS` means the intended main-agent/specialist ownership and required artifacts were preserved. `Protocol PASS` requires all three plus the artifact checks. Campaign count is descriptive only: one or several owned campaigns are allowed.

## Standard architecture aggregate comparison

{aggregate_table(arms)}

`Workflow cost` is the combined Standard workflow cost, including the GPT-5.4 main agent and the specialist. The Nemotron specialist endpoint itself costs $0; Nemotron's displayed workflow cost is paid GPT-5.4 main-agent usage, with one retained lower-bound cell where that paid usage was not preserved.

### Interpreting low Ackley repeats

The low Ackley observations are verified end-to-end outcomes, not missing data: each comparable cell has 60 unique evaluations, the requested BayBE backend, matching objective values, and a complete trajectory. Ackley 6D remains difficult at this budget, and the agent-authored BO configuration materially affects the result. GLM-5.1 repeats 1 and 2 independently selected the same deterministic configuration (seed 42, initial design 12, expected improvement) and therefore produced identical trajectories. Gemini repeats 2 and 3 likewise selected seed 42, initial design 10, and automatic acquisition and produced identical trajectories. These pairs measure reproducibility of the agent's configuration choice, but they are not independent optimizer-randomness draws. Sonnet repeat 2 is a valid low trajectory amid two materially stronger repeats; Nemotron's two valid Ackley repeats also differ substantially. No replacement is warranted unless the experimental question is changed to externally assigned, distinct seeds rather than end-to-end agent-selected workflows.

### All observed outcomes

This descriptive figure includes every run with a retained result, regardless of evaluation count. `X` markers are failed protocol cells and are annotated as `total/unique`; their values are outcomes, not equal-budget estimates.

![All observed results](figures/standard_all_observed_results.png)

### Equal-budget quality comparison

The following quality, AUC, and convergence figures use only protocol-comparable 60-evaluation trajectories. Failed runs remain visible in the all-outcomes figure and per-run tables below.

![Protocol-comparable quality and AUC](figures/standard_quality_auc_final.png)

![Convergence](figures/standard_convergence_final.png)

![Resources](figures/standard_resources_final.png)

![Reliability](figures/standard_reliability_final.png)

## Every requested Standard run

### Ackley 6D

{run_table(rows, CASES[0])}

### Direct Arylation

{run_table(rows, CASES[1])}

The dagger on a cell cost denotes a lower bound or unavailable total. A double dagger (`‡`) on AUC marks a retained descriptive/canonical AUC from a failed unequal-budget run; it is not used in equal-budget aggregates. Failed cells' observed best results, time, and measurable resources remain included in the all-results tables.

### Why evaluation counts differ from 60

There are {len(budget_failed_rows)} budget-invalid Standard cells: {earlier_budget_failures} are retained from the earlier matrix, {infrastructure_budget_failures} comes from the infrastructure-replacement cohort, and {prompt_budget_failures} occurred under the clarified shared-budget prompt. {over_budget} exceeded 60 evaluations and {under_budget} stopped below 60. One additional cell has exactly 60 evaluations but fails architecture compliance. The prompt-clarified failures are retained as model/agent budget-adherence outcomes, not attributed to the former smoke/full-campaign ambiguity.

The corrected prompt preserves the bounded smoke-test step while stating that every objective evaluation performed during smoke testing, debugging, or repeated execution counts toward the same total. BO-MCP does not impose a hard global cap because doing so would hide model budget-adherence behavior; the evaluator records and flags violations.

The prior duplicate-affected Ackley r03 cells for GPT-5.4, GLM-5.1, and Nemotron were replaced after correcting BayBE continuous duplicate resuggestions. GPT-5.4 and GLM-5.1 each completed one 60-result campaign with zero duplicates. Nemotron performed 60 unique objective evaluations; its first valid result remained in the local immutable artifact after an invalid submission payload, and the other 59 were submitted to BO-MCP. The report includes all 60 in its scientific trajectory and marks this provenance explicitly.

### Protocol failures and retained agent/model outcomes

{failure_table(rows)}

## Four-architecture comparison (GPT-5.4)

{architecture_table(arch_rows)}

### Every architecture repeat

{architecture_run_table(arch_runs)}

The architecture comparison uses the same two cases and three repeats. Standard delegates campaign authorship to the BO specialist and has the main agent execute it; Main-script has the main agent author/execute; Direct-tool exposes BO operations directly; No-BO-MCP removes BO-MCP and uses local optimization. The retained per-run architecture rows and trajectories are in `control/REPORT_DATA.json`.

The earlier frozen matrix reported a higher Direct Arylation AUC for Standard than for Main-script (0.941 versus 0.891). However, Standard repeats 1 and 2 in that matrix performed 62 and 61 total objective evaluations, respectively, so that value is retained only as descriptive historical evidence. The current equal-budget Standard replacements produced AUCs of 0.984, 0.679, and 0.931 (mean 0.865; sample SD 0.163), while Main-script produced 0.827, 0.915, and 0.932 (mean 0.891; sample SD 0.057). The 0.027 mean difference is driven by one weak Standard repeat and is small relative to the observed run-to-run variation; these three repeats do not support a strong claim that either architecture has better Direct Arylation sample efficiency. Standard reached a mean final yield of 100.00 versus 99.94 for Main-script.

![Architecture resources](figures/architecture_resources.png)

![Architecture quality](figures/architecture_quality_auc.svg)

![Architecture convergence](figures/architecture_convergence_final.png)

![Architecture AUC by evaluation horizon](figures/architecture_auc_horizons_final.png)

![Architecture reliability and campaigns](figures/architecture_reliability_campaigns_final.png)

![Architecture cost-quality comparison](figures/architecture_cost_quality_final.png)

## Cost completeness audit

Across all 66 model/architecture cells, {exact} are exact under the benchmark-date pricing schedule, {lower} are lower bounds, and {unavailable} are unavailable. “Exact” means every paid response has usage and a matching frozen public/list price. The Nemotron specialist cost is exactly $0 because these runs used NVIDIA's free developer endpoint; the displayed Nemotron workflow cost still includes the GPT-5.4 main agent. A genuine timeout can remain a lower bound if cancellation leaves a paid provider request with unresolved billing.

{cost_table(cost_cells)}

## Corrected infrastructure and replacement policy

The replacement cohort uses an append-only provider ledger, response-ID deduplication, frozen pricing, a read-only runtime with writable output/tmp areas, Claude’s explicit response allowance, local-only benchmark tools, Gemini-compatible tool-response conversion, BayBE for future runs, lightweight diagnostics readback, and unambiguous shared-budget smoke-test instructions. The {len(replacements)} selected replacements are enumerated with hashes in `control/SELECTION_AUDIT.json`. Initial infrastructure-aborted pilots are preserved but excluded. Failed tasks, retries, timeouts, extra campaigns, duplicate evaluations, and budget overruns are retained as observed outcomes and clearly marked; runs affected by the former smoke/full-budget wording are not described as pure model failures.

## Reproducibility

`control/REPORT_DATA.json` stores every plotted trajectory and all per-run rows. `control/FULL_COST_AUDIT.json` stores the 66-cell call/usage/cost reconciliation. `control/SELECTION_AUDIT.json` identifies replaced evidence and why. `control/benchmark_cost_rules_2026-08-06.json` freezes list-price rules. `control/REPORT_MANIFEST.sha256` hashes the report, data, audits, figures, and every selected replacement output.
"""


def evidence_entry(key: tuple[str, str, int], path: Path) -> dict[str, Any]:
    metrics = (
        path / "metrics_recovered.json"
        if (path / "metrics_recovered.json").is_file()
        else path / "metrics.json"
    )
    ledger = path / "provider_requests.jsonl"
    auxiliary = []
    for name in ("READBACK_RECOVERY_AUDIT.json", "FAILURE_DB_AUDIT.json"):
        audit = path.parents[4] / "control" / name
        if audit.is_file():
            auxiliary.append({"path": str(audit), "sha256": digest(audit)})
    return {
        "arm_id": key[0],
        "case": key[1],
        "repeat": key[2],
        "output": {
            "path": str(path / "output.json"),
            "sha256": digest(path / "output.json"),
        },
        "metrics": (
            {"path": str(metrics), "sha256": digest(metrics)}
            if metrics.is_file()
            else None
        ),
        "request_ledger": {"path": str(ledger), "sha256": digest(ledger)},
        "auxiliary_audits": auxiliary,
    }


def budget_audit_cells(
    standard_rows: list[dict[str, Any]], architecture_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_key = {}
    for row in architecture_rows + standard_rows:
        key = (row["arm_id"], row["case"], int(row["repeat"]))
        by_key[key] = {
            "arm_id": row["arm_id"],
            "case": row["case"],
            "repeat": int(row["repeat"]),
            "cell_id": row.get("cell_id"),
            "campaign_count_created": row.get("campaigns"),
            "global_result_count": row.get("global_result_count"),
            "global_unique_parameter_count": row.get("global_unique_parameter_count"),
            "global_duplicate_parameter_count": row.get(
                "global_duplicate_parameter_count"
            ),
            "global_budget_pass": row.get("global_budget_status") == "PASS",
            "global_budget_status": row.get("global_budget_status"),
        }
    return [by_key[key] for key in sorted(by_key)]


def enforce_comparable_standard_trajectories(
    rows: list[dict[str, Any]], trajectories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply one global 60-evaluation rule to retained and replacement cells."""
    trajectory_by_key = {
        (t["arm_id"], t["case"], int(t["repeat"])): t for t in trajectories
    }
    comparable_keys = set()
    for row in rows:
        key = (row["arm_id"], row["case"], int(row["repeat"]))
        trajectory = trajectory_by_key.get(key)
        total = row.get("global_result_count")
        unique = row.get("global_unique_parameter_count")
        duplicates = row.get("global_duplicate_parameter_count")
        budget_ok = total == 60
        scientifically_valid = unique == 60 and duplicates in (None, 0)
        complete_curve = bool(
            trajectory and len(trajectory.get("best_so_far", [])) == 60
        )
        comparable = (
            row.get("scientific_status") == "PASS"
            and budget_ok
            and scientifically_valid
            and complete_curve
        )
        row["global_budget_status"] = "PASS" if budget_ok else "FAIL"
        if comparable:
            comparable_keys.add(key)
            continue
        if row.get("observed_best_objective") is None:
            row["observed_best_objective"] = row.get("final_quality")
        if row.get("observed_normalized_auc_60") is None:
            row["observed_normalized_auc_60"] = row.get("normalized_auc_60")
        row["scientific_status"] = "FAIL"
        row["final_quality"] = None
        row["normalized_auc_60"] = None
        row["full_protocol_pass"] = False
    return [
        trajectory
        for key, trajectory in trajectory_by_key.items()
        if key in comparable_keys
    ]


def normalize_architecture_comparison(
    runs: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    cost_cells: list[dict[str, Any]],
) -> None:
    """Apply the global budget rule and recompute architecture quality summaries."""
    for row in runs:
        total = row.get("global_result_count")
        unique = row.get("global_unique_parameter_count")
        duplicates = row.get("global_duplicate_parameter_count")
        budget_ok = total == 60
        scientifically_valid = unique == 60 and duplicates in (None, 0)
        complete_quality = (
            row.get("final_quality") is not None
            and row.get("normalized_auc_60") is not None
        )
        row["global_budget_status"] = "PASS" if budget_ok else "FAIL"
        row["scientific_status"] = (
            "PASS"
            if budget_ok and scientifically_valid and complete_quality
            else "FAIL"
        )
        if row["scientific_status"] == "FAIL":
            row["observed_final_quality"] = row.get("final_quality")
            row["observed_normalized_auc_60"] = row.get("normalized_auc_60")
            row["final_quality"] = None
            row["normalized_auc_60"] = None
            row["full_protocol_pass"] = False

    for aggregate in aggregates:
        selected = [row for row in runs if row["arm_id"] == aggregate["architecture"]]
        cells = [
            cell for cell in cost_cells if cell["arm_id"] == aggregate["architecture"]
        ]
        cost = summarize_cost(cells)
        aggregate.update(
            {
                "campaigns": sum(int(row.get("campaigns") or 0) for row in selected),
                "strict_passes": sum(
                    row.get("strict_status") == "PASS" for row in selected
                ),
                "runtime_s": sum(float(row.get("runtime_s") or 0) for row in selected),
                "requests": cost["traced_provider_calls"],
                "total_tokens": sum(
                    sum(int(value) for value in model["tokens"].values())
                    for cell in cells
                    for model in cell["models"].values()
                ),
                "cost_status": cost["cost_status"],
                "total_cost_usd": cost["known_list_cost_usd"],
            }
        )
        aggregate["scientific"] = sum(
            row["scientific_status"] == "PASS" for row in selected
        )
        aggregate["protocol_passes"] = sum(
            row.get("full_protocol_pass") is True for row in selected
        )
        for case, prefix in ((CASES[0], "ackley"), (CASES[1], "direct")):
            case_rows = [
                row
                for row in selected
                if row["case"] == case and row["scientific_status"] == "PASS"
            ]
            final_values = [float(row["final_quality"]) for row in case_rows]
            auc_values = [float(row["normalized_auc_60"]) for row in case_rows]
            aggregate[f"{prefix}_final"] = (
                statistics.fmean(final_values) if final_values else None
            )
            aggregate[f"{prefix}_auc_60"] = (
                statistics.fmean(auc_values) if auc_values else None
            )


def build_architecture_trajectories(
    runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matrix = {
        (row["arm_id"], row["case"], int(row["repeat"])): row
        for row in load(MATRIX_TRAJECTORIES)["cells"]
        if row["arm_id"] in ARCH_IDS
    }
    trajectories = []
    for row in runs:
        key = (row["arm_id"], row["case"], int(row["repeat"]))
        curve = None
        source = None
        output_path = row.get("source_output_path")
        if output_path:
            metrics_path = Path(output_path).with_name("metrics.json")
            if metrics_path.is_file():
                metrics = load(metrics_path)
                block = (
                    metrics.get("local_artifacts", {})
                    if row["arm_id"] == "no_bo_gpt"
                    else metrics.get("bo_mcp", {})
                )
                curve = block.get("eval_best_so_far_curve") or block.get(
                    "best_so_far_by_evaluation"
                )
                source = str(metrics_path)
        if not isinstance(curve, list) or len(curve) != 60:
            retained = matrix.get(key)
            if retained:
                curve = retained.get("best_so_far")
                source = str(MATRIX_TRAJECTORIES)
        if not isinstance(curve, list) or len(curve) != 60:
            raise ValueError(f"missing 60-point architecture trajectory for {key}")
        curve = [float(value) for value in curve]
        if not math.isclose(
            curve[-1], float(row["final_quality"]), rel_tol=0, abs_tol=1e-9
        ):
            raise ValueError(f"architecture trajectory final value mismatch for {key}")
        trajectories.append(
            {
                "arm_id": row["arm_id"],
                "case": row["case"],
                "repeat": int(row["repeat"]),
                "cell_id": row["cell_id"],
                "best_so_far": curve,
                "source_path": source,
            }
        )
    return trajectories


def validate_report_inputs(
    paths: dict[tuple[str, str, int], Path],
    rows: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    cost_cells: list[dict[str, Any]],
    budget_cells: list[dict[str, Any]],
    architecture_trajectories: list[dict[str, Any]],
) -> None:
    expected = {
        (arm_id, case, repeat)
        for arm_id in IDS
        for case in CASES
        for repeat in range(1, 4)
    }
    row_keys = {(row["arm_id"], row["case"], int(row["repeat"])) for row in rows}
    expected_replacements = len(REPLACEMENT_SPECS) + len(PROMPT_ARCHITECTURE_SPECS)
    if len(paths) != expected_replacements or row_keys != expected:
        raise ValueError(
            "replacement selection or 48-cell Standard matrix is incomplete"
        )
    cost_keys = {
        (cell["arm_id"], cell["case"], int(cell["repeat"])) for cell in cost_cells
    }
    budget_keys = {
        (cell["arm_id"], cell["case"], int(cell["repeat"])) for cell in budget_cells
    }
    if len(cost_cells) != 66 or len(cost_keys) != 66:
        raise ValueError("full cost audit must contain 66 unique cells")
    if len(budget_cells) != 66 or len(budget_keys) != 66:
        raise ValueError("global budget audit must contain 66 unique cells")
    if any(len(trajectory.get("best_so_far", [])) != 60 for trajectory in trajectories):
        raise ValueError("every selected scientific trajectory must contain 60 points")
    if len(architecture_trajectories) != 24 or any(
        len(trajectory["best_so_far"]) != 60 for trajectory in architecture_trajectories
    ):
        raise ValueError(
            "architecture comparison must contain 24 complete trajectories"
        )
    for key, path in paths.items():
        cell = next(
            cell
            for cell in cost_cells
            if (cell["arm_id"], cell["case"], int(cell["repeat"])) == key
        )
        if cell["cost_status"] == "exact_calculated":
            model_total = sum(
                float(model["known_list_cost_usd"]) for model in cell["models"].values()
            )
            if not math.isclose(
                model_total,
                float(cell["known_list_cost_usd"]),
                rel_tol=0,
                abs_tol=1e-9,
            ):
                raise ValueError(f"model and cell costs do not reconcile for {key}")
        if not (path / "provider_requests.jsonl").is_file():
            raise ValueError(f"selected replacement has no request ledger: {path}")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    base = load(BASE_DATA)
    old_cost = load(BASE_COST)
    paths = selected_paths()
    architecture_paths = selected_architecture_paths()
    all_paths = paths | architecture_paths
    rows = [dict(row) for row in base["standard_run_rows"]]
    trajectories = [dict(t) for t in base["trajectories"]]
    replacement_rows = {}
    replacement_trajectories = {}
    for key, path in paths.items():
        row, trajectory = replacement_run(key, path)
        replacement_rows[key] = row
        if trajectory:
            replacement_trajectories[key] = trajectory
    rows = [
        replacement_rows.get((r["arm_id"], r["case"], int(r["repeat"])), r)
        for r in rows
    ]
    for row in rows:
        row["label"] = LABELS[row["arm_id"]]
        row.setdefault("evidence_source", "earlier_matrix")
        if (
            row["arm_id"],
            row["case"],
            int(row["repeat"]),
        ) == ("standard_nemotron", "direct_arylation", 2):
            row["architecture_failure_reason"] = (
                "specialist executed the full 60-point production campaign; "
                "Standard requires the main agent to execute the specialist-authored script"
            )
    trajectories = [
        t
        for t in trajectories
        if (t["arm_id"], t["case"], int(t["repeat"])) not in paths
    ]
    trajectories.extend(replacement_trajectories.values())
    trajectories = enforce_comparable_standard_trajectories(rows, trajectories)
    cost_cells = [
        dict(c)
        for c in old_cost["cells"]
        if (c["arm_id"], c["case"], int(c["repeat"])) not in all_paths
    ]
    cost_cells.extend(new_cost_cell(key, path) for key, path in all_paths.items())
    apply_nemotron_free_endpoint(cost_cells)
    patch_old_runtime(rows, old_cost)
    cost_map = {(c["arm_id"], c["case"], int(c["repeat"])): c for c in cost_cells}
    for row in rows:
        cell = cost_map[(row["arm_id"], row["case"], int(row["repeat"]))]
        row["cost_status"] = cell["cost_status"]
        row["cost_usd"] = float(cell.get("known_list_cost_usd") or 0)
    arms = [dict(a) for a in base["standard_arms"]]
    for arm in arms:
        aggregate_arm(arm, rows, trajectories, cost_cells)
    arm_cost = {
        arm: summarize_cost([c for c in cost_cells if c["arm_id"] == arm])
        for arm in set(c["arm_id"] for c in cost_cells)
    }
    full_cost = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "definition": load(RULES)["definition"],
        "arms": arm_cost,
        "cells": sorted(
            cost_cells, key=lambda c: (c["arm_id"], c["case"], c["repeat"])
        ),
    }
    (ROOT / "control/FULL_COST_AUDIT.json").write_text(
        json.dumps(full_cost, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "control/FULL_COST_AUDIT.md").write_text(
        "# Full 66-cell cost audit\n\n" + cost_table(cost_cells) + "\n",
        encoding="utf-8",
    )
    claude_cells = [
        cell
        for cell in cost_cells
        if cell["arm_id"] in {"standard_sonnet5", "standard_opus5"}
    ]
    claude_cost = {
        "schema_version": 2,
        "definition": full_cost["definition"],
        "summaries": {
            arm_id: arm_cost[arm_id]
            for arm_id in ("standard_sonnet5", "standard_opus5")
        },
        "cells": claude_cells,
    }
    (ROOT / "control/CLAUDE_COST_AUDIT.json").write_text(
        json.dumps(claude_cost, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    selection = {
        "schema_version": 1,
        "policy": "replace only infrastructure-defective cells; retain genuine model/agent failures",
        "selected_replacements": [
            evidence_entry(key, path) for key, path in sorted(all_paths.items())
        ],
        "excluded_pilots": ["standard_sonnet5_fixed", "standard_gemini_fixed"],
    }
    (ROOT / "control/SELECTION_AUDIT.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    arch_runs = [dict(row) for row in base["gpt_architecture_run_rows"]]
    architecture_replacement_rows = {
        key: replacement_run(key, path)[0] for key, path in architecture_paths.items()
    }
    architecture_replacement_rows.update(
        {
            (row["arm_id"], row["case"], int(row["repeat"])): dict(row)
            for row in rows
            if row["arm_id"] == "standard_gpt"
        }
    )
    arch_runs = [
        architecture_replacement_rows.get(
            (row["arm_id"], row["case"], int(row["repeat"])), row
        )
        for row in arch_runs
    ]
    arch_rows = [dict(row) for row in base["gpt_architecture_rows"]]
    patch_old_runtime(arch_runs, old_cost)
    normalize_architecture_comparison(arch_runs, arch_rows, cost_cells)
    architecture_trajectories = build_architecture_trajectories(arch_runs)
    budget_cells = budget_audit_cells(rows, arch_runs)
    budget_audit = {
        "schema_version": 2,
        "definition": "campaign count is diagnostic; budget passes with exactly 60 attempted objective evaluations in total, while duplicates are a separate scientific failure",
        "summary": {
            "cells": len(budget_cells),
            "passes": sum(cell["global_budget_pass"] for cell in budget_cells),
            "failures": sum(not cell["global_budget_pass"] for cell in budget_cells),
        },
        "cells": budget_cells,
    }
    validate_report_inputs(
        all_paths,
        rows,
        trajectories,
        cost_cells,
        budget_cells,
        architecture_trajectories,
    )
    (ROOT / "control/GLOBAL_BUDGET_AUDIT.json").write_text(
        json.dumps(budget_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    generated = datetime.now(timezone.utc).isoformat()
    data = {
        "generated_at": generated,
        "scope": "eight-model Standard and four-architecture GPT-5.4 comparison",
        "standard_arms": arms,
        "trajectories": sorted(
            trajectories, key=lambda t: (t["arm_id"], t["case"], t["repeat"])
        ),
        "standard_run_rows": rows,
        "gpt_architecture_rows": arch_rows,
        "gpt_architecture_run_rows": arch_runs,
        "gpt_architecture_trajectories": architecture_trajectories,
        "selection_audit": selection,
    }
    (ROOT / "control/REPORT_DATA.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    all_observed_plot(rows)
    quality_plot(trajectories)
    convergence_plot(trajectories)
    resource_plot(arms)
    reliability_plot(arms)
    architecture_quality_plot(arch_runs)
    architecture_resource_plot(arch_rows)
    architecture_convergence_plot(architecture_trajectories)
    architecture_auc_horizons_plot(architecture_trajectories)
    architecture_reliability_plot(arch_runs)
    architecture_efficiency_plot(arch_rows)
    report_text = report(
        generated, arms, rows, arch_rows, arch_runs, cost_cells, all_paths
    )
    (ROOT / "FULL_COMPARISON_REPORT.md").write_text(report_text, encoding="utf-8")
    # Replace the copied predecessor too, so the final directory has no stale
    # report entry under its former filename.
    (ROOT / "CLAUDE5_STANDARD_COMPARISON.md").write_text(report_text, encoding="utf-8")
    for name in ["benchmark_cost_rules_2026-08-06.json"]:
        (ROOT / "control" / name).write_bytes(RULES.read_bytes())
    files = [
        p for p in ROOT.rglob("*") if p.is_file() and p.name != "REPORT_MANIFEST.sha256"
    ]
    for path in all_paths.values():
        files.extend([path / "output.json", path / "provider_requests.jsonl"])
        metrics = (
            path / "metrics_recovered.json"
            if (path / "metrics_recovered.json").is_file()
            else path / "metrics.json"
        )
        if metrics.is_file():
            files.append(metrics)
        files.extend(
            audit
            for audit in (
                path.parents[4] / "control/READBACK_RECOVERY_AUDIT.json",
                path.parents[4] / "control/FAILURE_DB_AUDIT.json",
            )
            if audit.is_file()
        )
    manifest_lines = []
    for path in sorted(set(files)):
        try:
            display = path.relative_to(ROOT)
        except ValueError:
            display = path
        manifest_lines.append(f"{digest(path)}  {display}")
    (ROOT / "control/REPORT_MANIFEST.sha256").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
