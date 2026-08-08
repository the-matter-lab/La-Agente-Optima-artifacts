#!/usr/bin/env python3
"""Reconcile all retained benchmark responses against provider-call traces."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = REPORT_ROOT / "control/FULL_COST_AUDIT.json"
OUTPUT_MD = REPORT_ROOT / "control/FULL_COST_AUDIT.md"
PRICE_PATH = REPORT_ROOT / "control/benchmark_cost_rules_2026-08-06.json"

ORIGINAL_ROOT = Path(
    "/local-scratch/home/lynnfang00/research/"
    "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "full_matrix_20260730T154405Z"
)
NEMOTRON_ROOT = Path(
    "/local-scratch/home/lynnfang00/research/"
    "akg4pyscf-ackley-direct-arylation-evidence-20260729/outputs/bo_mcp_evals/"
    "nemotron_extension_20260803T171418Z"
)
GPT56_ROOT = Path(
    "/local-scratch/home/lynnfang00/research/"
    "akg4pyscf-gpt56-baybe-extension-20260804/outputs/bo_mcp_evals/"
    "gpt56_baybe_extension_20260805T025700Z"
)
CLAUDE_WORKTREE = Path(
    "/local-scratch/home/lynnfang00/research/"
    "akg4pyscf-claude5-baybe-extension-20260805"
)
SONNET_ROOT = (
    CLAUDE_WORKTREE
    / "outputs/bo_mcp_evals/claude_sonnet5_baybe_extension_20260805T215935Z"
)
OPUS_ROOT = (
    CLAUDE_WORKTREE
    / "outputs/bo_mcp_evals/claude_opus5_baybe_extension_20260805T215935Z"
)

RUN_SOURCES = (
    ("original_matrix", ORIGINAL_ROOT, "control/FULL_MATRIX_AUDIT.json"),
    ("nemotron_extension", NEMOTRON_ROOT, "control/NEMOTRON_EXTENSION_AUDIT.json"),
    ("gpt56_extension", GPT56_ROOT, "control/EXTENSION_AUDIT.json"),
    ("sonnet5_extension", SONNET_ROOT, "control/EXTENSION_AUDIT.json"),
    ("opus5_extension", OPUS_ROOT, "control/EXTENSION_AUDIT.json"),
)

ENDPOINT_MARKERS = {
    "openai_responses": "api.openai.com/v1/responses",
    "openrouter_chat_completions": "openrouter.ai/api/v1/chat/completions",
    "anthropic_messages": "api.anthropic.com/v1/messages",
    "nvidia_chat_completions": "integrate.api.nvidia.com/v1/chat/completions",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def integer(value: Any) -> int:
    return int(numeric(value))


def output_path_for(root: Path, cell: dict[str, Any]) -> Path:
    declared = cell.get("output_path")
    if not isinstance(declared, str):
        output = cell.get("output")
        if isinstance(output, dict):
            declared = output.get("path")
    if isinstance(declared, str):
        path = Path(declared)
        return path if path.is_absolute() else root / path
    case = str(cell["case"])
    return root / "arms" / str(cell["cell_id"]).split("_r0")[0].replace(
        "ackley_", "", 1
    ).replace("direct_arylation_", "", 1) / "cells" / str(cell["cell_id"]) / (
        f"eval/cases/{case}/output.json"
    )


def expected_output_hash(cell: dict[str, Any]) -> str | None:
    value = cell.get("output_sha256")
    if isinstance(value, str):
        return value
    output = cell.get("output")
    if isinstance(output, dict) and isinstance(output.get("sha256"), str):
        return output["sha256"]
    return None


def source_cells() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for cohort, root, audit_relative in RUN_SOURCES:
        audit_path = root / audit_relative
        audit = load_json(audit_path)
        cohort_cells = audit.get("cells")
        if not isinstance(cohort_cells, list):
            raise AssertionError(f"Missing cells in {audit_path}")
        for source_cell in cohort_cells:
            if not isinstance(source_cell, dict):
                raise AssertionError(f"Malformed cell in {audit_path}")
            output_path = output_path_for(root, source_cell)
            expected_hash = expected_output_hash(source_cell)
            actual_hash = sha256(output_path)
            if expected_hash and expected_hash != actual_hash:
                raise AssertionError(f"Output hash mismatch: {output_path}")
            selected.append(
                {
                    "cohort": cohort,
                    "root": root,
                    "source_cell": source_cell,
                    "output_path": output_path,
                    "output_sha256": actual_hash,
                }
            )
        sources.append(
            {
                "cohort": cohort,
                "run_root": str(root),
                "audit_path": str(audit_path),
                "audit_sha256": sha256(audit_path),
                "selected_cells": len(cohort_cells),
            }
        )
    if len(selected) != 66:
        raise AssertionError(f"Expected 66 selected cells, found {len(selected)}")
    cell_ids = [str(item["source_cell"]["cell_id"]) for item in selected]
    if len(cell_ids) != len(set(cell_ids)):
        raise AssertionError("Cell IDs are not unique")
    return selected, sources


def response_records(output: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_messages = output.get("raw_messages")
    if isinstance(raw_messages, list):
        records.extend(message for message in raw_messages if isinstance(message, dict))
    subagent_usage = output.get("subagent_usage")
    tasks = subagent_usage.get("tasks") if isinstance(subagent_usage, dict) else []
    if isinstance(tasks, list):
        for task in tasks:
            if not isinstance(task, dict):
                continue
            history = task.get("message_history")
            if isinstance(history, list):
                records.extend(message for message in history if isinstance(message, dict))
    return [record for record in records if record.get("kind") == "response"]


def comparable_response(record: dict[str, Any]) -> str:
    fields = {
        key: record.get(key)
        for key in (
            "model_name",
            "provider_name",
            "provider_response_id",
            "provider_url",
            "usage",
            "provider_details",
        )
    }
    return json.dumps(fields, sort_keys=True, default=str)


def deduplicate_responses(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    unique: dict[str, dict[str, Any]] = {}
    signatures: dict[str, str] = {}
    missing_id = 0
    conflicts = 0
    for record in records:
        response_id = record.get("provider_response_id")
        if not isinstance(response_id, str) or not response_id:
            missing_id += 1
            continue
        signature = comparable_response(record)
        if response_id in unique:
            if signatures[response_id] != signature:
                conflicts += 1
            continue
        unique[response_id] = record
        signatures[response_id] = signature
    return list(unique.values()), {
        "observed_response_records": len(records),
        "captured_unique_responses": len(unique),
        "duplicate_response_records": len(records) - len(unique) - missing_id,
        "response_records_without_id": missing_id,
        "conflicting_duplicate_records": conflicts,
    }


def trace_counts(controller_log: Path) -> dict[str, int]:
    text = controller_log.read_text(encoding="utf-8", errors="replace")
    counts = {
        name: text.count(marker) for name, marker in ENDPOINT_MARKERS.items()
    }
    counts["total_llm_posts"] = sum(counts.values())
    return counts


def token_counts(record: dict[str, Any]) -> dict[str, int]:
    usage = record.get("usage")
    if not isinstance(usage, dict):
        return {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    details = usage.get("details")
    details = details if isinstance(details, dict) else {}
    cache_read = integer(usage.get("cache_read_tokens"))
    cache_write = integer(usage.get("cache_write_tokens"))
    total_input = integer(usage.get("input_tokens"))
    explicit_uncached = details.get("input_tokens")
    if isinstance(explicit_uncached, (int, float)) and not isinstance(
        explicit_uncached, bool
    ):
        uncached = int(explicit_uncached)
    else:
        uncached = max(0, total_input - cache_read - cache_write)
    return {
        "input": uncached,
        "cache_write": cache_write,
        "cache_read": cache_read,
        "output": integer(usage.get("output_tokens")),
    }


def response_cost(
    record: dict[str, Any], rules: dict[str, Any]
) -> tuple[float | None, str]:
    model = record.get("model_name")
    rule = rules.get("models", {}).get(model)
    if not isinstance(rule, dict):
        return None, "missing_model_rule"
    method = rule.get("pricing_method")
    if method == "retained_upstream_inference_cost":
        details = record.get("provider_details")
        value = details.get("upstream_inference_cost") if isinstance(details, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value), method
        return None, "missing_upstream_inference_cost"
    if method == "frozen_public_token_rates":
        usage = record.get("usage")
        if not isinstance(usage, dict) or not usage:
            return None, "missing_usage"
        tokens = token_counts(record)
        value = sum(tokens[key] * float(rule[key]) for key in tokens) / 1_000_000
        return value, method
    return None, str(method or "missing_pricing_method")


def prior_reported_cost(output: dict[str, Any]) -> float | None:
    breakdown = output.get("cost_breakdown")
    combined = breakdown.get("combined") if isinstance(breakdown, dict) else None
    value = combined.get("cost_usd") if isinstance(combined, dict) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def task_statuses(output: dict[str, Any]) -> dict[str, Any]:
    usage = output.get("subagent_usage")
    tasks = usage.get("tasks") if isinstance(usage, dict) else []
    tasks = tasks if isinstance(tasks, list) else []
    statuses = Counter(
        str(task.get("status") or "unknown") for task in tasks if isinstance(task, dict)
    )
    return {
        "task_count": sum(statuses.values()),
        "task_status_counts": dict(sorted(statuses.items())),
        "failed_task_count": statuses.get("failed", 0),
    }


def audit_cell(item: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    source_cell = item["source_cell"]
    output_path = item["output_path"]
    output = load_json(output_path)
    records = response_records(output)
    unique, record_stats = deduplicate_responses(records)
    controller_log = output_path.parents[3] / "controller.log"
    traces = trace_counts(controller_log)
    traced = traces["total_llm_posts"]
    captured = record_stats["captured_unique_responses"]
    unmatched = max(0, traced - captured)
    untraced = max(0, captured - traced)

    model_rows: dict[str, dict[str, Any]] = {}
    unpriced_reasons: Counter[str] = Counter()
    for record in unique:
        model = str(record.get("model_name") or "<missing>")
        provider = str(record.get("provider_name") or "<missing>")
        row = model_rows.setdefault(
            model,
            {
                "provider": provider,
                "responses": 0,
                "responses_with_usage": 0,
                "tokens": {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0},
                "priced_responses": 0,
                "unpriced_responses": 0,
                "known_list_cost_usd": 0.0,
                "pricing_methods": set(),
            },
        )
        row["responses"] += 1
        if isinstance(record.get("usage"), dict) and record["usage"]:
            row["responses_with_usage"] += 1
        tokens = token_counts(record)
        for key, value in tokens.items():
            row["tokens"][key] += value
        cost, method = response_cost(record, rules)
        row["pricing_methods"].add(method)
        if cost is None:
            row["unpriced_responses"] += 1
            unpriced_reasons[method] += 1
        else:
            row["priced_responses"] += 1
            row["known_list_cost_usd"] += cost

    for row in model_rows.values():
        row["pricing_methods"] = sorted(row["pricing_methods"])
    known_cost = sum(row["known_list_cost_usd"] for row in model_rows.values())
    missing_usage = sum(
        row["responses"] - row["responses_with_usage"] for row in model_rows.values()
    )
    unpriced = sum(row["unpriced_responses"] for row in model_rows.values())
    metadata_clean = (
        record_stats["response_records_without_id"] == 0
        and record_stats["conflicting_duplicate_records"] == 0
        and missing_usage == 0
        and untraced == 0
    )
    token_status = "exact" if metadata_clean and unmatched == 0 else "lower_bound"
    traced_unpriced_provider = traces["nvidia_chat_completions"] > 0
    if unpriced or traced_unpriced_provider:
        cost_status = "unavailable"
    elif metadata_clean and unmatched == 0:
        cost_status = "exact_calculated"
    else:
        cost_status = "lower_bound"

    return {
        "cohort": item["cohort"],
        "arm_id": str(source_cell.get("arm_id") or output_path.parents[5].name),
        "cell_id": str(source_cell["cell_id"]),
        "case": str(source_cell["case"]),
        "repeat": int(source_cell["repeat"]),
        "output_path": str(output_path),
        "output_sha256": item["output_sha256"],
        "controller_log_path": str(controller_log),
        "controller_log_sha256": sha256(controller_log),
        "transport_trace": traces,
        **record_stats,
        "unmatched_traced_provider_calls": unmatched,
        "captured_responses_without_trace": untraced,
        "responses_without_usage": missing_usage,
        "models": dict(sorted(model_rows.items())),
        "known_list_cost_usd": known_cost,
        "prior_reported_combined_cost_usd": prior_reported_cost(output),
        "token_status": token_status,
        "cost_status": cost_status,
        "unpriced_response_count": unpriced,
        "unpriced_reasons": dict(
            sorted(
                (
                    unpriced_reasons
                    | (
                        Counter({"traced_provider_without_public_usd_price": 1})
                        if traced_unpriced_provider
                        else Counter()
                    )
                ).items()
            )
        ),
        **task_statuses(output),
    }


def summarize(cells: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[cell["arm_id"]].append(cell)
    result: dict[str, dict[str, Any]] = {}
    for arm, rows in sorted(grouped.items()):
        status_counts = Counter(row["cost_status"] for row in rows)
        if status_counts.get("unavailable"):
            arm_status = "unavailable"
        elif status_counts.get("lower_bound"):
            arm_status = "lower_bound"
        else:
            arm_status = "exact_calculated"
        result[arm] = {
            "cells": len(rows),
            "cost_status": arm_status,
            "cost_status_counts": dict(sorted(status_counts.items())),
            "traced_provider_calls": sum(
                row["transport_trace"]["total_llm_posts"] for row in rows
            ),
            "captured_unique_responses": sum(
                row["captured_unique_responses"] for row in rows
            ),
            "duplicate_response_records": sum(
                row["duplicate_response_records"] for row in rows
            ),
            "unmatched_traced_provider_calls": sum(
                row["unmatched_traced_provider_calls"] for row in rows
            ),
            "failed_task_count": sum(row["failed_task_count"] for row in rows),
            "known_list_cost_usd": sum(row["known_list_cost_usd"] for row in rows),
            "prior_reported_combined_cost_usd": sum(
                row["prior_reported_combined_cost_usd"] or 0.0 for row in rows
            ),
            "prior_reported_cost_cells": sum(
                row["prior_reported_combined_cost_usd"] is not None for row in rows
            ),
        }
    return result


def summarize_models(cells: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in cells:
        for model, source in cell["models"].items():
            row = result.setdefault(
                model,
                {
                    "provider": source["provider"],
                    "responses": 0,
                    "responses_with_usage": 0,
                    "tokens": {
                        "input": 0,
                        "cache_write": 0,
                        "cache_read": 0,
                        "output": 0,
                    },
                    "priced_responses": 0,
                    "unpriced_responses": 0,
                    "known_list_cost_usd": 0.0,
                    "pricing_methods": set(),
                },
            )
            row["responses"] += source["responses"]
            row["responses_with_usage"] += source["responses_with_usage"]
            for key, value in source["tokens"].items():
                row["tokens"][key] += value
            row["priced_responses"] += source["priced_responses"]
            row["unpriced_responses"] += source["unpriced_responses"]
            row["known_list_cost_usd"] += source["known_list_cost_usd"]
            row["pricing_methods"].update(source["pricing_methods"])
    for row in result.values():
        row["pricing_methods"] = sorted(row["pricing_methods"])
    return dict(sorted(result.items()))


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Full benchmark cost audit",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "This audit reconciles each retained provider response ID against the LLM POSTs "
        "in that cell's controller log. Repeated copies of the same response ID are "
        "counted once. `exact_calculated` means complete call/usage coverage and a frozen "
        "pricing rule; `lower_bound` means some traced calls lack retained responses; "
        "`unavailable` means at least one captured model has no authoritative USD list price.",
        "",
        "## Overall",
        "",
        f"- Cells: {payload['overall']['cells']}",
        f"- Exact: {payload['overall']['cost_status_counts'].get('exact_calculated', 0)}",
        f"- Lower bound: {payload['overall']['cost_status_counts'].get('lower_bound', 0)}",
        f"- Unavailable: {payload['overall']['cost_status_counts'].get('unavailable', 0)}",
        f"- Traced provider calls: {payload['overall']['traced_provider_calls']}",
        f"- Unique retained responses: {payload['overall']['captured_unique_responses']}",
        f"- Repeated response records removed: {payload['overall']['duplicate_response_records']}",
        f"- Traced calls without retained response usage: {payload['overall']['unmatched_traced_provider_calls']}",
        f"- Retained response records without ID: {payload['overall']['response_records_without_id']}",
        f"- Unique retained responses without usage: {payload['overall']['responses_without_usage']}",
        f"- Conflicting duplicate payloads: {payload['overall']['conflicting_duplicate_records']}",
        "",
        "## By arm",
        "",
        "| Arm | Cells | Exact | Lower | Unavailable | Calls | Unique responses | Duplicates removed | Unmatched | Known USD subtotal |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, row in payload["arms"].items():
        counts = row["cost_status_counts"]
        lines.append(
            f"| {arm} | {row['cells']} | {counts.get('exact_calculated', 0)} | "
            f"{counts.get('lower_bound', 0)} | {counts.get('unavailable', 0)} | "
            f"{row['traced_provider_calls']} | {row['captured_unique_responses']} | "
            f"{row['duplicate_response_records']} | {row['unmatched_traced_provider_calls']} | "
            f"${row['known_list_cost_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "The known subtotal is exact only where the arm status is "
            "`exact_calculated`; otherwise it is a partial/lower-bound subtotal.",
            "",
            "## Retained-output cost reconciliation",
            "",
            "| Arm | Prior cost-bearing cells | Prior retained total | Recalculated known subtotal | New arm status |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for arm, row in payload["arms"].items():
        lines.append(
            f"| {arm} | {row['prior_reported_cost_cells']}/{row['cells']} | "
            f"${row['prior_reported_combined_cost_usd']:.6f} | "
            f"${row['known_list_cost_usd']:.6f} | {row['cost_status']} |"
        )
    lines.extend(
        [
            "",
            "Prior totals are the combined costs embedded in retained `output.json` files. "
            "They are shown for reconciliation, not automatically accepted as correct: "
            "the new calculation uses unique response IDs and the frozen rules above.",
            "",
            "## By wire model",
            "",
            "| Wire model | Responses | Priced | Unpriced | Input | Cache write | Cache read | Output | Known USD subtotal |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for model, row in payload["models"].items():
        tokens = row["tokens"]
        lines.append(
            f"| {model} | {row['responses']} | {row['priced_responses']} | "
            f"{row['unpriced_responses']} | {tokens['input']} | {tokens['cache_write']} | "
            f"{tokens['cache_read']} | {tokens['output']} | ${row['known_list_cost_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Per cell",
            "",
            "| Cell | Status | Calls | Unique | Duplicates removed | Unmatched | Failed tasks | Known USD subtotal |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for cell in payload["cells"]:
        lines.append(
            f"| {cell['cell_id']} | {cell['cost_status']} | "
            f"{cell['transport_trace']['total_llm_posts']} | "
            f"{cell['captured_unique_responses']} | {cell['duplicate_response_records']} | "
            f"{cell['unmatched_traced_provider_calls']} | {cell['failed_task_count']} | "
            f"${cell['known_list_cost_usd']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The known USD subtotal is a complete list-price cost only for "
            "`exact_calculated` cells. It is a lower bound for `lower_bound` cells. For "
            "`unavailable` cells it includes only priced models and must not be presented "
            "as the cell's total cost.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    rules = load_json(PRICE_PATH)
    selected, sources = source_cells()
    cells = [audit_cell(item, rules) for item in selected]
    cells.sort(key=lambda row: (row["arm_id"], row["case"], row["repeat"]))

    all_ids: dict[str, str] = {}
    cross_cell_duplicates: list[dict[str, str]] = []
    for item in selected:
        output = load_json(item["output_path"])
        unique, _ = deduplicate_responses(response_records(output))
        for record in unique:
            response_id = str(record["provider_response_id"])
            prior = all_ids.get(response_id)
            if prior and prior != item["source_cell"]["cell_id"]:
                cross_cell_duplicates.append(
                    {"response_id": response_id, "first_cell": prior, "second_cell": item["source_cell"]["cell_id"]}
                )
            all_ids[response_id] = str(item["source_cell"]["cell_id"])
    if cross_cell_duplicates:
        raise AssertionError("Provider response IDs overlap across benchmark cells")
    if any(cell["captured_responses_without_trace"] for cell in cells):
        raise AssertionError("A cell has more retained responses than traced provider calls")

    status_counts = Counter(cell["cost_status"] for cell in cells)
    overall = {
        "cells": len(cells),
        "cost_status_counts": dict(sorted(status_counts.items())),
        "traced_provider_calls": sum(
            cell["transport_trace"]["total_llm_posts"] for cell in cells
        ),
        "captured_unique_responses": sum(
            cell["captured_unique_responses"] for cell in cells
        ),
        "duplicate_response_records": sum(
            cell["duplicate_response_records"] for cell in cells
        ),
        "unmatched_traced_provider_calls": sum(
            cell["unmatched_traced_provider_calls"] for cell in cells
        ),
        "known_list_cost_usd": sum(cell["known_list_cost_usd"] for cell in cells),
        "response_records_without_id": sum(
            cell["response_records_without_id"] for cell in cells
        ),
        "responses_without_usage": sum(cell["responses_without_usage"] for cell in cells),
        "conflicting_duplicate_records": sum(
            cell["conflicting_duplicate_records"] for cell in cells
        ),
        "unpriced_response_count": sum(
            cell["unpriced_response_count"] for cell in cells
        ),
        "cross_cell_duplicate_response_ids": 0,
    }
    expected_status_counts = {
        "exact_calculated": 46,
        "lower_bound": 14,
        "unavailable": 6,
    }
    if overall["cost_status_counts"] != expected_status_counts:
        raise AssertionError(
            f"Unexpected status counts: {overall['cost_status_counts']} != {expected_status_counts}"
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_version": "full-cost-audit-v1",
        "definition": (
            "Response-ID-deduplicated public/list inference cost at the benchmark date, "
            "reconciled against each cell's retained transport-level LLM POST trace."
        ),
        "price_rules": {
            "path": str(PRICE_PATH),
            "sha256": sha256(PRICE_PATH),
            "version": rules["version"],
        },
        "sources": sources,
        "overall": overall,
        "arms": summarize(cells),
        "models": summarize_models(cells),
        "rerun_scope_for_exact_cost": {
            "cells_with_missing_retained_responses": [
                cell["cell_id"] for cell in cells if cell["cost_status"] == "lower_bound"
            ],
            "count": sum(cell["cost_status"] == "lower_bound" for cell in cells),
            "unmatched_traced_provider_calls": sum(
                cell["unmatched_traced_provider_calls"]
                for cell in cells
                if cell["cost_status"] == "lower_bound"
            ),
            "note": (
                "These cells cannot become exact from the retained files alone. A provider-side "
                "historical usage export could avoid reruns; otherwise exact cost requires a replacement run."
            ),
        },
        "pricing_unavailable_scope": {
            "cells": [
                cell["cell_id"] for cell in cells if cell["cost_status"] == "unavailable"
            ],
            "count": sum(cell["cost_status"] == "unavailable" for cell in cells),
            "unmatched_traced_provider_calls": sum(
                cell["unmatched_traced_provider_calls"]
                for cell in cells
                if cell["cost_status"] == "unavailable"
            ),
            "note": (
                "Rerunning does not create a public USD-per-token price. NVIDIA documents free "
                "Developer Program prototyping access, but this audit conservatively does not "
                "equate an account entitlement with a universal model list price."
            ),
        },
        "cells": cells,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
