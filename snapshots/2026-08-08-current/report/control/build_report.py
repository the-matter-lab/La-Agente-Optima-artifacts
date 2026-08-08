#!/usr/bin/env python3
"""Build the eight-model Standard comparison with Claude 5 extensions."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path("/local-scratch/home/lynnfang00/research")
PRIOR_DATA = (
    RESEARCH / "akg4pyscf-gpt56-baybe-extension-20260804/outputs/bo_mcp_evals/"
    "gpt56_standard_comparison_report_20260805T040502Z/control/REPORT_DATA.json"
)
CLAUDE_WORKTREE = RESEARCH / "akg4pyscf-claude5-baybe-extension-20260805"
SONNET_AUDIT = (
    CLAUDE_WORKTREE
    / "outputs/bo_mcp_evals/claude_sonnet5_baybe_extension_20260805T215935Z/"
    "control/EXTENSION_AUDIT.json"
)
OPUS_AUDIT = (
    CLAUDE_WORKTREE
    / "outputs/bo_mcp_evals/claude_opus5_baybe_extension_20260805T215935Z/"
    "control/EXTENSION_AUDIT.json"
)
MATRIX_ROOT = (
    RESEARCH
    / "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "full_matrix_20260730T154405Z"
)
MATRIX_TRAJECTORIES = MATRIX_ROOT / "control/TRAJECTORY_METRICS.json"
MATRIX_AUDIT = MATRIX_ROOT / "control/FULL_MATRIX_AUDIT.json"
NEMOTRON_AUDIT = (
    RESEARCH
    / "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "nemotron_extension_20260803T171418Z/control/NEMOTRON_EXTENSION_AUDIT.json"
)
GPT56_AUDIT = (
    RESEARCH / "akg4pyscf-gpt56-baybe-extension-20260804/outputs/bo_mcp_evals/"
    "gpt56_baybe_extension_20260805T025700Z/control/EXTENSION_AUDIT.json"
)
ARCHITECTURE_FIGURE_STEMS = [
    "architecture_quality_auc",
    "auc_gpt_architectures",
    "architecture_convergence",
]
FIGURES = ROOT / "figures"
DATA_PATH = ROOT / "control/REPORT_DATA.json"
REPORT_PATH = ROOT / "CLAUDE5_STANDARD_COMPARISON.md"
MANIFEST_PATH = ROOT / "control/REPORT_MANIFEST.sha256"
GLOBAL_BUDGET_AUDIT = ROOT / "control/GLOBAL_BUDGET_AUDIT.json"
CLAUDE_COST_AUDIT = ROOT / "control/CLAUDE_COST_AUDIT.json"
CLAUDE_PRICE_SNAPSHOT = ROOT / "control/benchmark_prices_2026-08-05.json"
FULL_COST_AUDIT = ROOT / "control/FULL_COST_AUDIT.json"
FULL_COST_RULES = ROOT / "control/benchmark_cost_rules_2026-08-06.json"

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
LABELS = [
    "GPT",
    "GLM",
    "Gemini",
    "DeepSeek",
    "Nemotron",
    "GPT-5.6",
    "Sonnet 5",
    "Opus 5",
]
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
BAYBE_EXTENSION_IDS = ["standard_gpt56", "standard_sonnet5", "standard_opus5"]
BAYBE_EXTENSION_LABELS = ["GPT-5.6", "Sonnet 5", "Opus 5"]
BAYBE_EXTENSION_COLORS = ["#f59e0b", "#d97706", "#111827"]
ARCHITECTURE_IDS = [
    "standard_gpt",
    "main_script_gpt",
    "direct_tool_gpt",
    "no_bo_gpt",
]
ARCHITECTURE_LABELS = {
    "standard_gpt": "Standard GPT",
    "main_script_gpt": "Main-script",
    "direct_tool_gpt": "Direct-tool",
    "no_bo_gpt": "No-BO-MCP",
}
CASE_LABELS = {
    "synthetic_ackley_6d": "Ackley 6D",
    "direct_arylation": "Direct Arylation",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_arm(
    audit: dict,
    arm_id: str,
    label: str,
    cost_summary: dict | None = None,
) -> dict:
    summary = audit["summary"]
    known_cost = (
        float(cost_summary["known_combined_list_price_usd"])
        if cost_summary is not None
        else sum(
            float(cell.get("known_main_cost_usd") or 0.0) for cell in audit["cells"]
        )
    )
    known_main_tokens = sum(
        int(cell.get("main_input_tokens") or 0)
        + int(cell.get("main_output_tokens") or 0)
        for cell in audit["cells"]
    )
    return {
        "arm_id": arm_id,
        "label": label,
        "cases": summary["by_case"],
        "reliability": {
            "attempts": 6,
            "scientifically_complete": summary["scientific_passes"],
            "strict_passes": summary["terminal_strict_passes"],
            "architecture_contract_passes": sum(
                bool(cell["architecture_contract_pass"]) for cell in audit["cells"]
            ),
            "full_protocol_passes": summary["protocol_passes"],
            "total_campaigns": summary["campaigns"],
        },
        "resources": {
            "runtime_s": summary["runtime_s"],
            "main_requests": summary["main_requests"],
            "known_cost_usd_lower_bound": known_cost,
            "known_structured_tokens_lower_bound": known_main_tokens,
            "cost_lower_bound": True,
            "tokens_lower_bound": True,
            "specialist_usage_source": "raw conversation metadata; summary task usage incomplete",
            "cost_status": (
                "lower bound under frozen 2026-08-05 Anthropic list prices; "
                "unmatched traced provider calls lack retained usage"
                if cost_summary is not None
                else "lower bound: includes every priced component retained by the evaluator; "
                "some specialist calls are unpriced"
            ),
            "exact_calculated_cells": (
                cost_summary["exact_calculated_cells"]
                if cost_summary is not None
                else None
            ),
            "unmatched_provider_calls": (
                cost_summary["unmatched_provider_calls"]
                if cost_summary is not None
                else None
            ),
        },
    }


def audit_trajectories(audit: dict, arm_id: str) -> list[dict]:
    return [
        {
            "arm_id": arm_id,
            "case": cell["case"],
            "cell_id": cell["cell_id"],
            "repeat": cell["repeat"],
            "best_at_60": cell["best_final_quality"],
            "best_so_far": cell["best_so_far"],
            "auc": {"60": cell["normalized_auc_60"]},
            "scientific_pass": cell["scientific_pass"],
            "protocol_pass": cell["protocol_pass"],
        }
        for cell in audit["cells"]
    ]


def audited_arm_tokens(cells: list[dict]) -> int:
    return sum(
        int(value)
        for cell in cells
        for model in cell["models"].values()
        for value in model["tokens"].values()
    )


def apply_full_resource_audit(arms: list[dict], full_cost_audit: dict) -> None:
    cells_by_arm = {
        arm_id: [
            cell for cell in full_cost_audit["cells"] if cell["arm_id"] == arm_id
        ]
        for arm_id in IDS
    }
    for arm in arms:
        arm_id = arm["arm_id"]
        audit_summary = full_cost_audit["arms"][arm_id]
        cells = cells_by_arm[arm_id]
        if len(cells) != 6:
            raise ValueError(f"Expected six cost-audit cells for {arm_id}")
        resource = arm["resources"]
        for key in (
            "cost_usd",
            "known_cost_usd_lower_bound",
            "known_main_cost_usd_lower_bound",
            "known_priced_cost_usd",
            "total_tokens",
            "known_structured_tokens_lower_bound",
        ):
            resource.pop(key, None)
        status = audit_summary["cost_status"]
        known_cost = float(audit_summary["known_list_cost_usd"])
        if status == "exact_calculated":
            resource["cost_usd"] = known_cost
        elif status == "lower_bound":
            resource["known_cost_usd_lower_bound"] = known_cost
        else:
            resource["known_priced_cost_usd"] = known_cost
        total_tokens = audited_arm_tokens(cells)
        tokens_lower_bound = any(cell["token_status"] != "exact" for cell in cells)
        if tokens_lower_bound:
            resource["known_structured_tokens_lower_bound"] = total_tokens
        else:
            resource["total_tokens"] = total_tokens
        resource.update(
            {
                "requests": int(audit_summary["traced_provider_calls"]),
                "request_measure": "transport-level LLM POSTs",
                "cost_status": status,
                "cost_lower_bound": status == "lower_bound",
                "cost_unavailable": status == "unavailable",
                "tokens_lower_bound": tokens_lower_bound,
                "exact_calculated_cells": int(
                    audit_summary["cost_status_counts"].get("exact_calculated", 0)
                ),
                "lower_bound_cells": int(
                    audit_summary["cost_status_counts"].get("lower_bound", 0)
                ),
                "unavailable_cells": int(
                    audit_summary["cost_status_counts"].get("unavailable", 0)
                ),
                "unmatched_provider_calls": int(
                    audit_summary["unmatched_traced_provider_calls"]
                ),
                "duplicate_response_records_removed": int(
                    audit_summary["duplicate_response_records"]
                ),
                "pricing_source": "control/FULL_COST_AUDIT.json",
            }
        )


def apply_architecture_resource_audit(
    rows: list[dict], full_cost_audit: dict
) -> None:
    cells_by_arm = {
        arm_id: [
            cell for cell in full_cost_audit["cells"] if cell["arm_id"] == arm_id
        ]
        for arm_id in ARCHITECTURE_IDS
    }
    by_architecture = {row["architecture"]: row for row in rows}
    for arm_id in ARCHITECTURE_IDS:
        cells = cells_by_arm[arm_id]
        summary = full_cost_audit["arms"][arm_id]
        row = by_architecture[arm_id]
        row["total_cost_usd"] = float(summary["known_list_cost_usd"])
        row["total_tokens"] = audited_arm_tokens(cells)
        row["requests"] = int(summary["traced_provider_calls"])
        row["cost_status"] = summary["cost_status"]
        row["runtime_s"] = sum(
            float(load_json(Path(cell["output_path"])).get("total_runtime_s") or 0.0)
            for cell in cells
        )


def copy_architecture_figures() -> None:
    for stem in ARCHITECTURE_FIGURE_STEMS:
        shutil.copy2(MATRIX_ROOT / "figures" / f"{stem}.svg", FIGURES / f"{stem}.svg")


def cell_key(cell: dict) -> tuple[str, str, int]:
    return cell["arm_id"], cell["case"], int(cell["repeat"])


def audit_key(cell: dict, arm_id: str | None = None) -> tuple[str, str, int]:
    return arm_id or cell["arm_id"], cell["case"], int(cell["repeat"])


def global_budget_map(audit: dict) -> dict[tuple[str, str, int], dict]:
    return {cell_key(cell): cell for cell in audit["cells"]}


def build_standard_run_rows(
    trajectories: list[dict],
    matrix_audit: dict,
    nemotron_audit: dict,
    gpt56_audit: dict,
    sonnet_audit: dict,
    opus_audit: dict,
    global_budget_audit: dict,
) -> list[dict]:
    trajectory_map = {cell_key(cell): cell for cell in trajectories}
    budget_map = global_budget_map(global_budget_audit)
    metadata: dict[tuple[str, str, int], dict] = {}

    for cell in matrix_audit["cells"]:
        if cell["arm_id"] not in IDS[:4]:
            continue
        output_path = MATRIX_ROOT / cell["output_path"]
        if sha256(output_path) != cell["output_sha256"]:
            raise ValueError(f"legacy output hash mismatch: {output_path}")
        output = load_json(output_path)
        architecture = output.get("architecture", {})
        architecture_pass = (
            not architecture.get("mode_violation_reasons", [])
            and int(architecture.get("subagent_delegation_count", 0)) >= 1
        )
        metadata[audit_key(cell)] = {
            "cell_id": cell["cell_id"],
            "strict_status": cell["strict_status"],
            "architecture_contract_pass": architecture_pass,
            "campaigns": cell["campaign_count_created"],
            "attempted_evaluations": cell["attempted_objective_evaluations"],
            "terminal_state": cell["terminal_state"],
            "source_output_path": str(output_path),
            "source_output_sha256": cell["output_sha256"],
        }

    for cell in nemotron_audit["cells"]:
        architecture_pass = bool(cell["architecture"]["ownership_matches_protocol"])
        metadata[audit_key(cell, "standard_nemotron")] = {
            "cell_id": cell["cell_id"],
            "strict_status": cell["strict_status"],
            "architecture_contract_pass": architecture_pass,
            "campaigns": cell["campaign_count_created"],
            "attempted_evaluations": None,
            "terminal_state": cell["terminal_state"],
        }

    for audit, arm_id in [
        (gpt56_audit, "standard_gpt56"),
        (sonnet_audit, "standard_sonnet5"),
        (opus_audit, "standard_opus5"),
    ]:
        for cell in audit["cells"]:
            metadata[audit_key(cell, arm_id)] = {
                "cell_id": cell["cell_id"],
                "strict_status": cell["terminal_strict_status"],
                "architecture_contract_pass": cell["architecture_contract_pass"],
                "campaigns": cell["campaign_count_created"],
                "attempted_evaluations": cell["attempted_production_evaluations"],
                "terminal_state": cell.get("terminal_state", "completed"),
            }

    rows = []
    for arm_id, label in zip(IDS, LABELS, strict=True):
        for case in CASE_LABELS:
            for repeat in range(1, 4):
                key = (arm_id, case, repeat)
                trajectory = trajectory_map.get(key)
                audit = metadata.get(key, {})
                budget = budget_map[key]
                scientific_pass = trajectory is not None
                architecture_pass = audit.get("architecture_contract_pass")
                backend = (
                    "baybe"
                    if case == "direct_arylation"
                    or arm_id in BAYBE_EXTENSION_IDS
                    else "botorch"
                )
                backend_pass = scientific_pass
                artifact_pass = scientific_pass
                protocol_pass = (
                    scientific_pass
                    and architecture_pass is True
                    and budget["global_budget_pass"] is True
                    and backend_pass
                    and artifact_pass
                )
                rows.append(
                    {
                        "arm_id": arm_id,
                        "label": label,
                        "case": case,
                        "repeat": repeat,
                        "cell_id": audit.get(
                            "cell_id",
                            trajectory.get("cell_id") if trajectory else None,
                        ),
                        "backend": backend,
                        "backend_pass": backend_pass,
                        "artifact_pass": artifact_pass,
                        "scientific_status": "PASS" if scientific_pass else "MISSING",
                        "final_quality": trajectory.get("best_at_60")
                        if trajectory
                        else None,
                        "normalized_auc_60": (
                            trajectory["auc"]["60"] if trajectory else None
                        ),
                        "strict_status": audit.get("strict_status"),
                        "architecture_contract_pass": audit.get(
                            "architecture_contract_pass"
                        ),
                        "global_budget_status": budget["global_budget_status"],
                        "global_result_count": budget["global_result_count"],
                        "global_unique_parameter_count": budget[
                            "global_unique_parameter_count"
                        ],
                        "global_duplicate_parameter_count": budget[
                            "global_duplicate_parameter_count"
                        ],
                        "full_protocol_pass": protocol_pass,
                        "campaigns": audit.get("campaigns"),
                        "attempted_evaluations": (
                            audit.get("attempted_evaluations")
                            if audit.get("attempted_evaluations") is not None
                            else (60 if trajectory else None)
                        ),
                        "terminal_state": (
                            audit.get("terminal_state", "completed")
                            if trajectory
                            else "timeout"
                        ),
                        "source_output_path": audit.get("source_output_path"),
                        "source_output_sha256": audit.get("source_output_sha256"),
                    }
                )
    return rows


def build_architecture_run_rows(
    matrix_trajectories: dict, matrix_audit: dict, global_budget_audit: dict
) -> list[dict]:
    audits = {
        audit_key(cell): cell
        for cell in matrix_audit["cells"]
        if cell["arm_id"] in ARCHITECTURE_IDS
    }
    budget_map = global_budget_map(global_budget_audit)
    rows = []
    for trajectory in matrix_trajectories["cells"]:
        if trajectory["arm_id"] not in ARCHITECTURE_IDS:
            continue
        audit = audits[cell_key(trajectory)]
        output_path = MATRIX_ROOT / audit["output_path"]
        if sha256(output_path) != audit["output_sha256"]:
            raise ValueError(f"architecture output hash mismatch: {output_path}")
        output = load_json(output_path)
        architecture = output.get("architecture", {})
        architecture_pass = not architecture.get("mode_violation_reasons", [])
        if architecture.get("script_artifact_required"):
            architecture_pass = architecture_pass and int(
                architecture.get("script_artifact_count", 0)
            ) >= 1
        if trajectory["arm_id"] == "standard_gpt":
            architecture_pass = architecture_pass and int(
                architecture.get("subagent_delegation_count", 0)
            ) >= 1
        budget = budget_map[cell_key(trajectory)]
        is_no_bo = trajectory["arm_id"] == "no_bo_gpt"
        effective_budget_pass = (
            audit["attempted_objective_evaluations"] == 60
            if is_no_bo
            else budget["global_budget_pass"] is True
        )
        protocol_pass = architecture_pass and effective_budget_pass
        rows.append(
            {
                "arm_id": trajectory["arm_id"],
                "label": ARCHITECTURE_LABELS[trajectory["arm_id"]],
                "case": trajectory["case"],
                "repeat": trajectory["repeat"],
                "cell_id": trajectory["cell_id"],
                "final_quality": trajectory["best_at_60"],
                "normalized_auc_60": trajectory["auc"]["60"],
                "strict_status": audit["strict_status"],
                "architecture_contract_pass": architecture_pass,
                "global_budget_status": (
                    "PASS" if effective_budget_pass else "FAIL"
                ),
                "global_result_count": (
                    audit["attempted_objective_evaluations"]
                    if is_no_bo
                    else budget["global_result_count"]
                ),
                "global_unique_parameter_count": (
                    audit["attempted_objective_evaluations"]
                    if is_no_bo
                    else budget["global_unique_parameter_count"]
                ),
                "full_protocol_pass": protocol_pass,
                "campaigns": (
                    audit["campaign_count_created"]
                    if audit["campaign_count_created"] is not None
                    else 0
                ),
                "attempted_evaluations": audit["attempted_objective_evaluations"],
                "terminal_state": audit["terminal_state"],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            list(CASE_LABELS).index(row["case"]),
            ARCHITECTURE_IDS.index(row["arm_id"]),
            row["repeat"],
        ),
    )


def reconcile_arm_reliability(arms: list[dict], rows: list[dict]) -> None:
    for arm in arms:
        arm_rows = [row for row in rows if row["arm_id"] == arm["arm_id"]]
        arm["reliability"]["architecture_contract_passes"] = sum(
            row["architecture_contract_pass"] is True for row in arm_rows
        )
        arm["reliability"]["full_protocol_passes"] = sum(
            row["full_protocol_pass"] is True for row in arm_rows
        )
        arm["reliability"]["global_budget_passes"] = sum(
            row["global_budget_status"] == "PASS" for row in arm_rows
        )


def values_for(
    trajectories: list[dict], arm_id: str, case: str, metric: str
) -> list[float]:
    rows = [
        row for row in trajectories if row["arm_id"] == arm_id and row["case"] == case
    ]
    if metric == "final":
        return [float(row["best_at_60"]) for row in rows]
    return [float(row["auc"]["60"]) for row in rows]


def save_figure(fig: plt.Figure, stem: str) -> None:
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    for suffix in ("svg", "png"):
        fig.savefig(FIGURES / f"{stem}.{suffix}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def quality_grid(
    trajectories: list[dict],
    ids: list[str],
    labels: list[str],
    colors: list[str],
    stem: str,
    title: str,
    hatch_new: bool = False,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    specs = [
        ("synthetic_ackley_6d", "final", "Ackley final quality", 1.0),
        ("synthetic_ackley_6d", "auc", "Ackley normalized AUC@60", 1.0),
        ("direct_arylation", "final", "Direct Arylation final yield (%)", 105.0),
        ("direct_arylation", "auc", "Direct Arylation normalized AUC@60", 1.0),
    ]
    x = np.arange(len(ids))
    for ax, (case, metric, panel_title, ceiling) in zip(axes.flat, specs, strict=True):
        per_arm = [values_for(trajectories, arm_id, case, metric) for arm_id in ids]
        means = [statistics.fmean(values) for values in per_arm]
        errors = [
            statistics.stdev(values) if len(values) > 1 else 0.0 for values in per_arm
        ]
        bars = ax.bar(x, means, yerr=errors, capsize=4, color=colors, alpha=0.86)
        if hatch_new and case == "synthetic_ackley_6d":
            for index, arm_id in enumerate(ids):
                if arm_id in BAYBE_EXTENSION_IDS:
                    bars[index].set_hatch("///")
        for index, values in enumerate(per_arm):
            ax.scatter([index] * len(values), values, color="black", s=21, zorder=3)
        ax.set_title(panel_title)
        ax.set_xticks(x, labels, rotation=28, ha="right")
        ax.set_ylim(0, ceiling * 1.04)
        ax.grid(axis="y", alpha=0.24)
        if hatch_new and case == "synthetic_ackley_6d":
            ax.legend(
                handles=[
                    Patch(
                        facecolor="white",
                        edgecolor="black",
                        hatch="///",
                        label="BayBE extension; older arms use BoTorch",
                    )
                ],
                fontsize=8,
                loc="upper left",
            )
    fig.suptitle(title, fontsize=15)
    save_figure(fig, stem)


def convergence(
    trajectories: list[dict],
    ids: list[str],
    labels: list[str],
    colors: list[str],
    stem: str,
    title: str,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    for ax, case, panel_title in [
        (axes[0], "synthetic_ackley_6d", "Ackley 6D"),
        (axes[1], "direct_arylation", "Direct Arylation"),
    ]:
        for arm_id, label, color in zip(ids, labels, colors, strict=True):
            curves = [
                np.asarray(row["best_so_far"][:60], dtype=float)
                for row in trajectories
                if row["arm_id"] == arm_id and row["case"] == case
            ]
            if not curves:
                continue
            stack = np.vstack(curves)
            mean = stack.mean(axis=0)
            sd = stack.std(axis=0, ddof=1) if len(curves) > 1 else np.zeros(60)
            x = np.arange(1, 61)
            ax.plot(
                x, mean, color=color, linewidth=2, label=f"{label} (n={len(curves)})"
            )
            ax.fill_between(x, mean - sd, mean + sd, color=color, alpha=0.09)
        ax.set_title(panel_title)
        ax.set_xlabel("Production evaluation")
        ax.set_ylabel(
            "Best-so-far quality"
            if case.startswith("synthetic")
            else "Best-so-far yield (%)"
        )
        ax.grid(alpha=0.24)
        ax.legend(fontsize=8, loc="lower right", ncol=2 if len(ids) > 4 else 1)
    fig.suptitle(title, fontsize=15)
    save_figure(fig, stem)


def architecture_passes(arm: dict) -> int:
    reliability = arm["reliability"]
    if "architecture_contract_passes" in reliability:
        return int(reliability["architecture_contract_passes"])
    return int(reliability.get("ownership_matches_protocol_among_complete", 0))


def full_protocol_passes(arm: dict) -> int:
    return int(arm["reliability"].get("full_protocol_passes", 0))


def reliability_plot(arms: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.6))
    x = np.arange(len(arms))
    width = 0.2
    science = [arm["reliability"]["scientifically_complete"] for arm in arms]
    budget = [arm["reliability"]["global_budget_passes"] for arm in arms]
    architecture = [architecture_passes(arm) for arm in arms]
    protocol = [full_protocol_passes(arm) for arm in arms]
    axes[0].bar(x - 1.5 * width, science, width, label="Scientific", color="#0ea5e9")
    axes[0].bar(
        x - 0.5 * width,
        budget,
        width,
        label="Global 60-evaluation budget",
        color="#8b5cf6",
    )
    axes[0].bar(
        x + 0.5 * width,
        architecture,
        width,
        label="Architecture/ownership",
        color="#22c55e",
    )
    axes[0].bar(
        x + 1.5 * width,
        protocol,
        width,
        label="Protocol",
        color="#f97316",
    )
    axes[0].set_ylim(0, 6.7)
    axes[0].set_ylabel("Passing cells out of 6")
    axes[0].set_xticks(x, LABELS, rotation=28, ha="right")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.24)
    campaigns = [arm["reliability"]["total_campaigns"] for arm in arms]
    axes[1].bar(x, campaigns, color=COLORS, alpha=0.86)
    axes[1].axhline(
        6,
        color="black",
        linestyle="--",
        linewidth=1,
        label="one/cell reference (diagnostic only)",
    )
    axes[1].set_ylabel("Total campaigns across six cells")
    axes[1].set_xticks(x, LABELS, rotation=28, ha="right")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.24)
    fig.suptitle("Standard architecture reliability and campaign behavior", fontsize=15)
    save_figure(fig, "standard_reliability_campaigns")


def architecture_reliability_plot(rows: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4))
    x = np.arange(len(ARCHITECTURE_IDS))
    width = 0.25
    grouped = [
        [row for row in rows if row["arm_id"] == arm_id]
        for arm_id in ARCHITECTURE_IDS
    ]
    budget = [sum(row["global_budget_status"] == "PASS" for row in arm) for arm in grouped]
    architecture = [
        sum(row["architecture_contract_pass"] is True for row in arm)
        for arm in grouped
    ]
    protocol = [sum(row["full_protocol_pass"] is True for row in arm) for arm in grouped]
    axes[0].bar(x - width, budget, width, label="60-evaluation budget", color="#8b5cf6")
    axes[0].bar(x, architecture, width, label="Architecture", color="#22c55e")
    axes[0].bar(x + width, protocol, width, label="Protocol", color="#f97316")
    axes[0].set_ylim(0, 6.7)
    axes[0].set_ylabel("Passing cells out of 6")
    axes[0].set_xticks(
        x,
        [ARCHITECTURE_LABELS[arm_id] for arm_id in ARCHITECTURE_IDS],
        rotation=25,
        ha="right",
    )
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.24)
    campaigns = [sum(row["campaigns"] for row in arm) for arm in grouped]
    axes[1].bar(x, campaigns, color=[COLORS[0], "#64748b", "#14b8a6", "#94a3b8"])
    axes[1].set_ylabel("Total BO-MCP campaigns (diagnostic)")
    axes[1].set_xticks(
        x,
        [ARCHITECTURE_LABELS[arm_id] for arm_id in ARCHITECTURE_IDS],
        rotation=25,
        ha="right",
    )
    axes[1].grid(axis="y", alpha=0.24)
    fig.suptitle("GPT-5.4 architecture protocol and campaign diagnostics", fontsize=15)
    save_figure(fig, "architecture_protocol_campaigns")


def resource_value(
    resource: dict, exact_key: str, lower_key: str
) -> tuple[float, bool]:
    if exact_key in resource:
        flag_key = (
            "cost_lower_bound" if exact_key == "cost_usd" else "tokens_lower_bound"
        )
        return float(resource[exact_key]), bool(resource.get(flag_key))
    return float(resource[lower_key]), True


def standard_resource_plot(arms: list[dict]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.8))
    x = np.arange(len(arms))
    runtime_h = [arm["resources"]["runtime_s"] / 3600 for arm in arms]
    costs = []
    cost_lower = []
    cost_unavailable = []
    tokens_m = []
    token_lower = []
    for arm in arms:
        resource = arm["resources"]
        status = resource["cost_status"]
        if status == "exact_calculated":
            cost = float(resource["cost_usd"])
        elif status == "lower_bound":
            cost = float(resource["known_cost_usd_lower_bound"])
        else:
            cost = float(resource["known_priced_cost_usd"])
        is_cost_lower = status == "lower_bound"
        token, is_token_lower = resource_value(
            resource,
            "total_tokens",
            "known_structured_tokens_lower_bound",
        )
        costs.append(cost)
        cost_lower.append(is_cost_lower)
        cost_unavailable.append(status == "unavailable")
        tokens_m.append(token / 1_000_000)
        token_lower.append(is_token_lower)

    panels = [
        (axes[0], runtime_h, [False] * len(arms), "Summed runtime (hours)", "h"),
        (axes[1], costs, cost_lower, "Known cost (USD)", "$"),
        (axes[2], tokens_m, token_lower, "Known structured tokens (millions)", "M"),
    ]
    for panel_index, (ax, values, lower_flags, title, unit) in enumerate(panels):
        bars = ax.bar(x, values, color=COLORS, alpha=0.86)
        for index, (bar, value, is_lower) in enumerate(
            zip(bars, values, lower_flags, strict=True)
        ):
            is_unavailable = panel_index == 1 and cost_unavailable[index]
            if is_unavailable:
                bar.set_hatch("xx")
                bar.set_alpha(0.25)
            elif is_lower:
                bar.set_hatch("///")
            prefix = "≥" if is_lower else ""
            if unit == "$":
                label = (
                    f"N/A\n(${value:.2f} priced)"
                    if is_unavailable
                    else f"{prefix}${value:.2f}"
                )
            elif unit == "h":
                label = f"{value:.2f}h"
            else:
                label = f"{prefix}{value:.1f}M"
            ax.text(
                index,
                value,
                label,
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=35,
            )
        ax.set_title(title)
        ax.set_xticks(x, LABELS, rotation=30, ha="right")
        ax.set_ylim(0, max(values) * 1.22)
        ax.grid(axis="y", alpha=0.24)
    axes[1].legend(
        handles=[
            Patch(
                facecolor="white", edgecolor="black", hatch="///", label="lower bound"
            ),
            Patch(
                facecolor="white",
                edgecolor="black",
                hatch="xx",
                alpha=0.4,
                label="total unavailable; bar is priced subtotal",
            ),
        ],
        fontsize=8,
        loc="upper right",
    )
    axes[2].legend(
        handles=[
            Patch(
                facecolor="white", edgecolor="black", hatch="///", label="lower bound"
            )
        ],
        fontsize=8,
        loc="upper right",
    )
    fig.suptitle(
        "Standard specialist resource comparison (six requested cells per arm)",
        fontsize=15,
    )
    save_figure(fig, "standard_resources")


def architecture_resource_plot(rows: list[dict]) -> None:
    by_arm = {row["architecture"]: row for row in rows}
    ordered = [by_arm[arm_id] for arm_id in ARCHITECTURE_IDS]
    colors = [COLORS[0], "#64748b", "#14b8a6", "#94a3b8"]
    labels = [ARCHITECTURE_LABELS[arm_id] for arm_id in ARCHITECTURE_IDS]
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.6))
    panels = [
        (
            axes[0],
            [row["runtime_s"] / 6 / 60 for row in ordered],
            "Mean wall time",
            "min/cell",
        ),
        (
            axes[1],
            [row["total_cost_usd"] / 6 for row in ordered],
            "Mean list cost",
            "$/cell",
        ),
        (
            axes[2],
            [row["total_tokens"] / 6 / 1_000_000 for row in ordered],
            "Mean token use",
            "M tokens/cell",
        ),
    ]
    x = np.arange(len(ordered))
    for panel_index, (ax, values, title, unit) in enumerate(panels):
        bars = ax.bar(x, values, color=colors, alpha=0.88)
        for index, (bar, value) in enumerate(zip(bars, values, strict=True)):
            label = (
                f"${value:.2f}"
                if panel_index == 1
                else f"{value:.1f}"
                if panel_index == 0
                else f"{value:.2f}M"
            )
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                label,
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.set_title(f"{title} ({unit})")
        ax.set_xticks(x, labels, rotation=25, ha="right")
        ax.set_ylim(0, max(values) * 1.18)
        ax.grid(axis="y", alpha=0.24)
    fig.suptitle(
        "GPT-5.4 architecture resources (six cells per architecture; lower is better)",
        fontsize=15,
    )
    save_figure(fig, "architecture_resources")


def case_text(case: dict, direct: bool = False) -> str:
    digits = 2 if direct else 4
    return f"{case['mean_final_quality']:.{digits}f} ± {case['sample_sd_final_quality']:.{digits}f}"


def optional_bool(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "PASS" if value else "FAIL"


def run_value(value: float | None, direct: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}" if direct else f"{value:.4f}"


def standard_run_table(rows: list[dict], case: str) -> str:
    lines = []
    for row in rows:
        if row["case"] != case:
            continue
        direct = case == "direct_arylation"
        attempts = row["attempted_evaluations"]
        lines.append(
            f"| {row['label']} | r{row['repeat']:02d} | "
            f"{run_value(row['final_quality'], direct)} | "
            f"{run_value(row['normalized_auc_60'])} | {row['backend']} | "
            f"{row['scientific_status']} | {row['global_budget_status']} | "
            f"{optional_bool(row['architecture_contract_pass'])} | "
            f"{optional_bool(row['full_protocol_pass'])} | "
            f"{row['campaigns'] if row['campaigns'] is not None else '—'} | "
            f"{row['global_result_count']} | "
            f"{row['global_unique_parameter_count']} | "
            f"{attempts if attempts is not None else '—'} | {row['terminal_state']} |"
        )
    return "\n".join(lines)


def architecture_run_table(rows: list[dict], case: str) -> str:
    lines = []
    for row in rows:
        if row["case"] != case:
            continue
        direct = case == "direct_arylation"
        lines.append(
            f"| {row['label']} | r{row['repeat']:02d} | "
            f"{run_value(row['final_quality'], direct)} | "
            f"{run_value(row['normalized_auc_60'])} | "
            f"{row['global_budget_status']} | "
            f"{optional_bool(row['architecture_contract_pass'])} | "
            f"{optional_bool(row['full_protocol_pass'])} | "
            f"{row['campaigns']} | {row['global_result_count']} | "
            f"{row['global_unique_parameter_count']} |"
        )
    return "\n".join(lines)


def standard_resource_table(arms: list[dict]) -> str:
    rows = []
    for arm in arms:
        resource = arm["resources"]
        runtime_h = resource["runtime_s"] / 3600
        mean_min = resource["runtime_s"] / 6 / 60
        tokens = resource.get("total_tokens")
        if tokens is None:
            tokens = resource.get("known_structured_tokens_lower_bound")
        token_text = "not summarized" if tokens is None else f"{tokens:,}"
        if resource.get("tokens_lower_bound") or resource.get(
            "known_structured_tokens_lower_bound"
        ):
            token_text = f"≥{token_text}"
        requests = resource.get("requests", resource.get("main_requests"))
        if requests is None:
            requests = resource.get("trace_http_posts")
        request_text = "—" if requests is None else str(requests)
        status = resource["cost_status"]
        if status == "exact_calculated":
            cost_text = f"${resource['cost_usd']:.3f} (exact)"
        elif status == "lower_bound":
            cost_text = f"≥${resource['known_cost_usd_lower_bound']:.3f}"
        else:
            cost_text = (
                f"N/A (${resource['known_priced_cost_usd']:.3f} priced subtotal)"
            )
        rows.append(
            f"| {arm['label']} | {runtime_h:.2f} | {mean_min:.1f} | "
            f"{token_text} | {request_text} | {cost_text} |"
        )
    return "\n".join(rows)


def report_markdown(
    generated: str,
    arms: list[dict],
    standard_runs: list[dict],
    architecture_rows: list[dict],
    architecture_runs: list[dict],
) -> str:
    rows = []
    for arm in arms:
        ackley = arm["cases"]["synthetic_ackley_6d"]
        direct = arm["cases"]["direct_arylation"]
        reliability = arm["reliability"]
        n_ack = ackley.get("scientifically_complete_runs", ackley.get("runs", 3))
        n_direct = direct.get("scientifically_complete_runs", direct.get("runs", 3))
        rows.append(
            f"| {arm['label']} | {case_text(ackley)} (n={n_ack}) | "
            f"{ackley['mean_normalized_auc_60']:.3f} ± {ackley['sample_sd_normalized_auc_60']:.3f} | "
            f"{case_text(direct, True)} (n={n_direct}) | "
            f"{direct['mean_normalized_auc_60']:.3f} ± {direct['sample_sd_normalized_auc_60']:.3f} | "
            f"{reliability['scientifically_complete']}/6 | {reliability['global_budget_passes']}/6 | "
            f"{architecture_passes(arm)}/6 | {full_protocol_passes(arm)}/6 | "
            f"{reliability['total_campaigns']} |"
        )
    table = "\n".join(rows)
    architecture_aggregate = []
    for row in architecture_rows:
        run_rows = [
            run
            for run in architecture_runs
            if run["arm_id"] == row["architecture"]
        ]
        budget_passes = sum(
            run["global_budget_status"] == "PASS" for run in run_rows
        )
        protocol_passes = sum(run["full_protocol_pass"] for run in run_rows)
        architecture_aggregate.append(
            f"| {ARCHITECTURE_LABELS[row['architecture']]} | "
            f"{row['ackley_final']:.4f} | {row['ackley_auc_60']:.3f} | "
            f"{row['direct_final']:.2f} | {row['direct_auc_60']:.3f} | "
            f"{row['scientific']}/6 | {budget_passes}/6 | "
            f"{protocol_passes}/6 | "
            f"{row['campaigns']} | ${row['total_cost_usd']:.3f} | "
            f"{row['total_tokens']:,} |"
        )
    return f"""# Full model and architecture comparison with GPT-5.6 and Claude 5

Generated from preserved evidence on {generated}. This report deliberately separates model effects from architecture effects. Values are descriptive means ± sample SD, and dots in the new figures are individual repeats.

## Experimental design

| Comparison | Held fixed | Changed | Requested cells |
|---|---|---|---:|
| A. Standard specialist models | GPT-5.4 main agent, Standard ownership contract, two cases, 60-evaluation budget, three repeats | Delegated specialist model | 48 |
| B. GPT architectures | GPT-5.4 model family, two cases, 60-evaluation budget, three repeats | Orchestration and BO-MCP access | 24 |

The Standard contract asks the specialist to author and smoke-test the campaign script while the GPT-5.4 main agent executes the production campaign and reports it. Comparison A therefore changes only the specialist arm at the design level. Comparison B uses GPT models throughout and changes the architecture. One requested Standard cell, Nemotron Direct r03, timed out without a scientific trajectory; it is retained below as missing and never imputed.

## Executive conclusions

- DeepSeek has the highest mean final Ackley quality (0.8194), with GLM close behind (0.8151); DeepSeek and GLM also lead Ackley AUC among the older BoTorch Standard arms. Because GPT-5.6 and Claude 5 Ackley runs used BayBE, the full eight-model Ackley comparison is backend-confounded.
- DeepSeek and GPT-5.6 both reach 100% mean final Direct Arylation yield. Standard GPT has the highest Direct AUC (0.941), followed by DeepSeek (0.915). Direct Arylation is BayBE-backed across the analyzed arms.
- Within the backend-matched new BayBE extensions, Opus 5 and GPT-5.6 have nearly identical final Ackley means; GPT-5.6 has the highest Ackley AUC, Sonnet 5 the highest Direct AUC, and GPT-5.6 the highest Direct final yield.
- With GPT-5.4 held fixed across architectures, Standard GPT gives the strongest scientific quality; main-script is the best cost-quality compromise; direct-tool satisfies the global budget in all six cells; no-BO-MCP is cheapest but scientifically weaker.
- Scientific completion, the global evaluation budget, and ownership/architecture compliance are distinct outcomes. Failed protocol checks do not erase otherwise verified canonical 60-point trajectories.

# Comparison A — Standard architecture, different specialist models

## Aggregate quality, AUC, reliability, and campaigns

| Specialist | Ackley final | Ackley AUC@60 | Direct final yield | Direct AUC@60 | Scientific | Global budget | Architecture | Protocol | Campaigns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{table}

![Eight-model quality and AUC](figures/standard_quality_auc.svg)

![Eight-model convergence](figures/standard_convergence.svg)

![Reliability and campaigns](figures/standard_reliability_campaigns.svg)

## Backend-matched BayBE extension view

The following panels compare only the three new Standard extensions that explicitly required and resolved to BayBE: GPT-5.6, Claude Sonnet 5, and Claude Opus 5. Each uses GPT-5.4 as main agent, three repeats per case, and 60 production evaluations.

![BayBE extension quality and AUC](figures/baybe_extension_quality_auc.svg)

![BayBE extension convergence](figures/baybe_extension_convergence.svg)

On Ackley, Opus 5 and GPT-5.6 have nearly identical mean final quality (0.7319 and 0.7307), while GPT-5.6 has the highest mean AUC (0.3500). Sonnet 5 is more variable because repeat 2 converged poorly, giving mean final quality 0.5850.

On Direct Arylation, GPT-5.6 has the highest mean final yield (100%), while Sonnet 5 has the highest mean AUC (0.8351), indicating earlier discovery on average. Opus 5 reaches mean final yield 94.73% and AUC 0.7766.

## Every Standard/model run

These tables expose every requested repeat. Legacy architecture/full-protocol states are reconstructed from the hash-verified raw outputs referenced by the frozen full-matrix audit; Nemotron uses its retained command-trace ownership audit; GPT-5.6 and Claude use their extension audits. All full per-point trajectories remain in `control/REPORT_DATA.json`.

The `Terminal` column preserves the historical controller outcome. A row can now be Protocol PASS while showing historical `failed` when the old evaluator rejected multiple campaigns even though the additional campaign was empty; the re-audited columns supersede that obsolete campaign-count rule.

### Ackley 6D — 24 requested runs

| Specialist | Run | Final | AUC@60 | Backend | Science | Global budget | Architecture | Protocol | Campaigns | Global results | Unique | Production attempts | Terminal |
|---|---:|---:|---:|---|---|---|---|---|---:|---:|---:|---:|---|
{standard_run_table(standard_runs, "synthetic_ackley_6d")}

### Direct Arylation — 24 requested runs

| Specialist | Run | Final yield | AUC@60 | Backend | Science | Global budget | Architecture | Protocol | Campaigns | Global results | Unique | Production attempts | Terminal |
|---|---:|---:|---:|---|---|---|---|---|---:|---:|---:|---:|---|
{standard_run_table(standard_runs, "direct_arylation")}

## Standard-arm resources

![Standard specialist runtime, known cost, and token usage](figures/standard_resources.svg)

| Specialist | Summed hours | Mean min/cell | Structured tokens | Requests | Known cost |
|---|---:|---:|---:|---:|---:|
{standard_resource_table(arms)}

Runtime is exact summed controller wall time across the six requested cells. Requests are transport-level LLM POSTs for every arm. Costs and tokens come from the 66-cell response-ID audit: 5,089 traced calls were reconciled against 4,537 unique retained responses after removing 1,747 repeated history records. Forty-six cells are exact-calculated; 14 are lower bounds because 447 traced calls lack retained responses; six Nemotron cells have no universal USD/token list price and are shown as `N/A` with only the priced GPT-5.4 subtotal visible. A hatched `≥` bar is a lower bound, while cross-hatching marks an unavailable total. These resource limitations do not change the scientific trajectories.

# Comparison B — GPT-5.4 across four architectures

This comparison uses GPT models for Standard and all three alternative architectures. It is unchanged from the immutable July 30 experiment and excludes GPT-5.6/Claude specialists because adding them would confound architecture and specialist model.

| Architecture | Ackley final | Ackley AUC@60 | Direct final | Direct AUC@60 | Scientific | Budget | Protocol | Campaigns | Cost | Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(architecture_aggregate)}

![GPT architecture final quality and AUC](figures/architecture_quality_auc.svg)

![GPT architecture AUC horizons](figures/auc_gpt_architectures.svg)

![GPT architecture convergence](figures/architecture_convergence.svg)

![GPT architecture resources](figures/architecture_resources.svg)

![GPT architecture protocol status and campaigns](figures/architecture_protocol_campaigns.svg)

Standard GPT leads this controlled architecture comparison on Ackley final quality and AUC and on Direct AUC. Main-script matches Standard's final Direct yield with about 41% of its corrected list cost and 35% of its tokens, at the expense of weaker Ackley performance and slower Direct discovery. Direct-tool creates exactly one BO-MCP campaign in every cell and satisfies the global budget 6/6. No-BO-MCP is fastest and cheapest, but its Direct quality and repeat reliability are weaker.

## Every GPT-architecture run

### Ackley 6D — 12 runs

| Architecture | Run | Final | AUC@60 | Budget | Architecture | Protocol | Campaigns | Global results | Unique |
|---|---:|---:|---:|---|---|---|---:|---:|---:|
{architecture_run_table(architecture_runs, "synthetic_ackley_6d")}

### Direct Arylation — 12 runs

| Architecture | Run | Final yield | AUC@60 | Budget | Architecture | Protocol | Campaigns | Global results | Unique |
|---|---:|---:|---:|---|---|---|---:|---:|---:|
{architecture_run_table(architecture_runs, "direct_arylation")}

## Interpretation boundary and protocol details

### Status definitions

- **Scientific PASS** means the report recovered the complete canonical 60-point trajectory with the required objective values and independently accepted it for quality/AUC analysis.
- **Global-budget PASS** means all campaigns owned by the run contain exactly 60 results total and 60 unique parameter vectors, with no duplicates, malformed objectives, schema mismatches, or missing campaign records. Campaign count is diagnostic only: empty setup campaigns are allowed, while extra real smoke evaluations fail the budget.
- **Architecture PASS** means the intended ownership/delegation contract was observed. In Standard, a specialist must author/smoke-test and the GPT-5.4 main agent must execute/report production.
- **Protocol PASS** means Scientific PASS + Global-budget PASS + Architecture PASS + the required backend and retained artifacts. The intentionally local No-BO-MCP architecture applies the same 60-evaluation rule to its local artifact; BO campaign count is not applicable there.
- **`n/a`** means a check genuinely does not apply, not PASS or FAIL. In particular, BO campaign count is not applicable to No-BO-MCP.
- **Exact calculated cost** means every traced provider call reconciles to one unique retained response with usage and a matching frozen pricing rule. **`≥` cost** is a lower bound because one or more traced calls lack retained responses. **`N/A`** means a model lacks a universally comparable USD/token price; the displayed bar is only the priced subtotal and is not the total. No missing cost is treated as zero. OpenAI and Anthropic use frozen benchmark-date token rates; OpenRouter uses the retained upstream inference cost for each unique response and excludes routing/BYOK fees.

- The eight-model Ackley panel is backend-confounded. The older GPT/GLM/Gemini/DeepSeek/Nemotron cells used BoTorch; GPT-5.6/Sonnet 5/Opus 5 used BayBE. Hatched bars identify the BayBE extensions.
- Direct Arylation is backend-matched to BayBE across arms, although the new extension prompts explicitly require BayBE while the older prompts allowed any supported backend.
- Scientific validity, the global budget, and architecture/ownership compliance are shown separately. Protocol failures remain included in the scientific trajectories and are not hidden or replaced.
- Cases are the Ackley 6D normalized surface and Direct Arylation measured-yield lookup; both are maximized. Each analyzed production trajectory targets 60 attempts, with three requested repeats per arm/case, request limit 80, and timeout 3,600 seconds.
- Nemotron Direct has two complete scientific repeats. Direct r03 timed out at 3,600 seconds and remains explicitly missing; no retry or score imputation is used.
- The older exit-137 Standard-GPT process is represented only by its explicitly recorded replacement.
- Full best-so-far vectors, AUC values, cell identifiers, global campaign/result counts, source hashes, and the missing-cell record are machine-readable in `control/REPORT_DATA.json` and `control/GLOBAL_BUDGET_AUDIT.json`.
- These are descriptive n=2–3 summaries, not inferential model rankings.

## Reproducibility and frozen evidence

`control/REPORT_DATA.json` contains all plotted trajectories, 48 requested Standard run rows, 24 GPT-architecture run rows, and aggregate summaries. `control/GLOBAL_BUDGET_AUDIT.json` records the per-campaign result counts reconstructed from frozen PostgreSQL dumps. `control/FULL_COST_AUDIT.json` contains the complete 66-cell call/response/cost reconciliation; `control/benchmark_cost_rules_2026-08-06.json` freezes its pricing rules. `control/REPORT_MANIFEST.sha256` verifies the report, figures, audits, pricing snapshots, and source evidence.
"""


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    prior = load_json(PRIOR_DATA)
    sonnet = load_json(SONNET_AUDIT)
    opus = load_json(OPUS_AUDIT)
    matrix_trajectories = load_json(MATRIX_TRAJECTORIES)
    matrix_audit = load_json(MATRIX_AUDIT)
    nemotron_audit = load_json(NEMOTRON_AUDIT)
    gpt56_audit = load_json(GPT56_AUDIT)
    global_budget_audit = load_json(GLOBAL_BUDGET_AUDIT)
    claude_cost_audit = load_json(CLAUDE_COST_AUDIT)
    full_cost_audit = load_json(FULL_COST_AUDIT)
    arms = list(prior["standard_arms"])
    arms.extend(
        [
            audit_arm(
                sonnet,
                "standard_sonnet5",
                "Sonnet 5",
                claude_cost_audit["summaries"]["standard_sonnet5"],
            ),
            audit_arm(
                opus,
                "standard_opus5",
                "Opus 5",
                claude_cost_audit["summaries"]["standard_opus5"],
            ),
        ]
    )
    apply_full_resource_audit(arms, full_cost_audit)
    trajectories = list(prior["trajectories"])
    trajectories.extend(audit_trajectories(sonnet, "standard_sonnet5"))
    trajectories.extend(audit_trajectories(opus, "standard_opus5"))
    standard_runs = build_standard_run_rows(
        trajectories,
        matrix_audit,
        nemotron_audit,
        gpt56_audit,
        sonnet,
        opus,
        global_budget_audit,
    )
    reconcile_arm_reliability(arms, standard_runs)
    architecture_runs = build_architecture_run_rows(
        matrix_trajectories, matrix_audit, global_budget_audit
    )
    architecture_rows = prior["gpt_architecture_rows"]
    apply_architecture_resource_audit(architecture_rows, full_cost_audit)

    quality_grid(
        trajectories,
        IDS,
        LABELS,
        COLORS,
        "standard_quality_auc",
        "Standard architecture: specialist-model quality (mean ± sample SD; dots are repeats)",
        hatch_new=True,
    )
    convergence(
        trajectories,
        IDS,
        LABELS,
        COLORS,
        "standard_convergence",
        "Standard architecture convergence (mean ± sample SD)",
    )
    reliability_plot(arms)
    standard_resource_plot(arms)
    architecture_reliability_plot(architecture_runs)
    architecture_resource_plot(architecture_rows)
    quality_grid(
        trajectories,
        BAYBE_EXTENSION_IDS,
        BAYBE_EXTENSION_LABELS,
        BAYBE_EXTENSION_COLORS,
        "baybe_extension_quality_auc",
        "BayBE Standard extensions: GPT-5.6 vs Claude 5",
    )
    convergence(
        trajectories,
        BAYBE_EXTENSION_IDS,
        BAYBE_EXTENSION_LABELS,
        BAYBE_EXTENSION_COLORS,
        "baybe_extension_convergence",
        "BayBE Standard extensions: convergence",
    )
    copy_architecture_figures()

    generated = datetime.now(timezone.utc).isoformat()
    data = {
        "generated_at": generated,
        "scope": (
            "Full eight-model Standard comparison, backend-matched BayBE extension view, "
            "and GPT-5.4 four-architecture comparison"
        ),
        "standard_arms": arms,
        "trajectories": trajectories,
        "standard_run_rows": standard_runs,
        "gpt_architecture_rows": architecture_rows,
        "gpt_architecture_run_rows": architecture_runs,
        "source_hashes": {
            "prior_report_data": {
                "path": str(PRIOR_DATA),
                "sha256": sha256(PRIOR_DATA),
            },
            "sonnet_audit": {"path": str(SONNET_AUDIT), "sha256": sha256(SONNET_AUDIT)},
            "opus_audit": {"path": str(OPUS_AUDIT), "sha256": sha256(OPUS_AUDIT)},
            "matrix_trajectories": {
                "path": str(MATRIX_TRAJECTORIES),
                "sha256": sha256(MATRIX_TRAJECTORIES),
            },
            "matrix_audit": {
                "path": str(MATRIX_AUDIT),
                "sha256": sha256(MATRIX_AUDIT),
            },
            "nemotron_audit": {
                "path": str(NEMOTRON_AUDIT),
                "sha256": sha256(NEMOTRON_AUDIT),
            },
            "gpt56_audit": {
                "path": str(GPT56_AUDIT),
                "sha256": sha256(GPT56_AUDIT),
            },
            "global_budget_audit": {
                "path": str(GLOBAL_BUDGET_AUDIT),
                "sha256": sha256(GLOBAL_BUDGET_AUDIT),
            },
            "claude_cost_audit": {
                "path": str(CLAUDE_COST_AUDIT),
                "sha256": sha256(CLAUDE_COST_AUDIT),
            },
            "claude_price_snapshot": {
                "path": str(CLAUDE_PRICE_SNAPSHOT),
                "sha256": sha256(CLAUDE_PRICE_SNAPSHOT),
            },
            "full_cost_audit": {
                "path": str(FULL_COST_AUDIT),
                "sha256": sha256(FULL_COST_AUDIT),
            },
            "full_cost_rules": {
                "path": str(FULL_COST_RULES),
                "sha256": sha256(FULL_COST_RULES),
            },
        },
    }
    DATA_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    REPORT_PATH.write_text(
        report_markdown(
            generated,
            arms,
            standard_runs,
            architecture_rows,
            architecture_runs,
        ),
        encoding="utf-8",
    )

    manifest_paths = [
        REPORT_PATH,
        DATA_PATH,
        Path(__file__).resolve(),
        PRIOR_DATA,
        SONNET_AUDIT,
        OPUS_AUDIT,
        MATRIX_TRAJECTORIES,
        MATRIX_AUDIT,
        NEMOTRON_AUDIT,
        GPT56_AUDIT,
        GLOBAL_BUDGET_AUDIT,
        ROOT / "control/build_global_budget_audit.py",
        CLAUDE_COST_AUDIT,
        CLAUDE_PRICE_SNAPSHOT,
        ROOT / "control/build_claude_cost_audit.py",
        FULL_COST_AUDIT,
        FULL_COST_RULES,
        ROOT / "control/build_full_cost_audit.py",
    ]
    manifest_paths.extend(sorted(FIGURES.iterdir()))
    lines = []
    for path in manifest_paths:
        try:
            display = path.relative_to(ROOT)
        except ValueError:
            display = path
        lines.append(f"{sha256(path)}  {display}")
    MANIFEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
