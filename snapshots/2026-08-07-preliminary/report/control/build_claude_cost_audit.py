#!/usr/bin/env python3
"""Reconstruct captured Claude usage under frozen 2026-08-05 list prices."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.bo_mcp.usage_metrics import main_cost_breakdown


ROOT = Path(__file__).resolve().parents[1]
WORKTREE = Path("/local-scratch/home/lynnfang00/research/akg4pyscf-claude5-baybe-extension-20260805")
PRICE_PATH = ROOT / "control/benchmark_prices_2026-08-05.json"
OUTPUT_PATH = ROOT / "control/CLAUDE_COST_AUDIT.json"
RUNS = {
    "standard_sonnet5": WORKTREE
    / "outputs/bo_mcp_evals/claude_sonnet5_baybe_extension_20260805T215935Z",
    "standard_opus5": WORKTREE
    / "outputs/bo_mcp_evals/claude_opus5_baybe_extension_20260805T215935Z",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def response_usage(messages: list[Any]) -> dict[str, Any]:
    seen: set[str] = set()
    observed = 0
    duplicates = 0
    tokens = {"input": 0, "cache_write_5m": 0, "cache_read": 0, "output": 0}
    missing_response_id = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("kind") != "response":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict) or not usage:
            continue
        observed += 1
        response_id = message.get("provider_response_id")
        if not isinstance(response_id, str) or not response_id:
            missing_response_id += 1
            continue
        if response_id in seen:
            duplicates += 1
            continue
        seen.add(response_id)
        details = usage.get("details") if isinstance(usage.get("details"), dict) else {}
        cache_read = number(usage.get("cache_read_tokens"))
        cache_write = number(usage.get("cache_write_tokens"))
        uncached_input = number(details.get("input_tokens"))
        if not uncached_input:
            uncached_input = max(
                0,
                number(usage.get("input_tokens")) - cache_read - cache_write,
            )
        tokens["input"] += uncached_input
        tokens["cache_write_5m"] += cache_write
        tokens["cache_read"] += cache_read
        tokens["output"] += number(usage.get("output_tokens"))
    return {
        "observed_response_records": observed,
        "captured_unique_responses": len(seen),
        "duplicate_response_records": duplicates,
        "usage_records_without_response_id": missing_response_id,
        "tokens": tokens,
    }


def list_price_cost(tokens: dict[str, int], prices: dict[str, float]) -> float:
    return sum(tokens[key] * float(prices[key]) for key in tokens) / 1_000_000


def main() -> None:
    price_snapshot = load_json(PRICE_PATH)
    cells: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    for arm_id, run_root in RUNS.items():
        audit_path = run_root / "control/EXTENSION_AUDIT.json"
        audit = load_json(audit_path)
        audit_cells = {cell["cell_id"]: cell for cell in audit["cells"]}
        output_paths = sorted(run_root.glob("arms/*/cells/*/eval/cases/*/output.json"))
        for output_path in output_paths:
            output = load_json(output_path)
            cell_id = output_path.parents[3].name
            audit_cell = audit_cells[cell_id]
            tasks = output.get("subagent_usage", {}).get("tasks", [])
            history = [
                message
                for task in tasks
                if isinstance(task, dict)
                for message in (task.get("message_history") or [])
            ]
            specialist = response_usage(history)
            model_id = audit_cell["specialist_provider_trace"]["expected_model"]
            prices = price_snapshot["models"][model_id]
            specialist_cost = list_price_cost(specialist["tokens"], prices)
            traced_calls = int(
                audit_cell["specialist_provider_trace"]["anthropic_messages_calls"]
            )
            unmatched_calls = max(
                0, traced_calls - specialist["captured_unique_responses"]
            )
            main_cost = main_cost_breakdown(output.get("raw_messages", []))
            main_subtotal = float(main_cost.get("cost_usd") or 0.0)
            complete = (
                bool(main_cost.get("cost_complete"))
                and unmatched_calls == 0
                and specialist["usage_records_without_response_id"] == 0
            )
            cells.append(
                {
                    "arm_id": arm_id,
                    "cell_id": cell_id,
                    "case": audit_cell["case"],
                    "repeat": audit_cell["repeat"],
                    "model_id": model_id,
                    "provider": "anthropic",
                    "provider_calls_traced": traced_calls,
                    **specialist,
                    "unmatched_provider_calls": unmatched_calls,
                    "specialist_captured_list_price_usd": specialist_cost,
                    "main_list_price_usd": main_subtotal,
                    "known_combined_list_price_usd": main_subtotal + specialist_cost,
                    "cost_complete": complete,
                    "cost_status": "exact_calculated" if complete else "lower_bound",
                    "output_path": str(output_path),
                    "output_sha256": sha256(output_path),
                }
            )
        sources.append(
            {
                "arm_id": arm_id,
                "extension_audit_path": str(audit_path),
                "extension_audit_sha256": sha256(audit_path),
            }
        )
    summaries: dict[str, dict[str, Any]] = {}
    for arm_id in RUNS:
        arm_cells = [cell for cell in cells if cell["arm_id"] == arm_id]
        summaries[arm_id] = {
            "cells": len(arm_cells),
            "exact_calculated_cells": sum(cell["cost_complete"] for cell in arm_cells),
            "lower_bound_cells": sum(not cell["cost_complete"] for cell in arm_cells),
            "provider_calls_traced": sum(
                cell["provider_calls_traced"] for cell in arm_cells
            ),
            "captured_unique_responses": sum(
                cell["captured_unique_responses"] for cell in arm_cells
            ),
            "unmatched_provider_calls": sum(
                cell["unmatched_provider_calls"] for cell in arm_cells
            ),
            "known_combined_list_price_usd": sum(
                cell["known_combined_list_price_usd"] for cell in arm_cells
            ),
            "specialist_captured_list_price_usd": sum(
                cell["specialist_captured_list_price_usd"] for cell in arm_cells
            ),
            "cost_status": (
                "exact_calculated"
                if all(cell["cost_complete"] for cell in arm_cells)
                else "lower_bound"
            ),
        }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "definition": (
            "Deduplicated captured provider responses priced under the frozen "
            "2026-08-05 list-price snapshot. Unmatched traced calls keep a cell "
            "as a lower bound until usage or confirmed non-billable status is recovered."
        ),
        "price_snapshot": {
            "path": str(PRICE_PATH),
            "sha256": sha256(PRICE_PATH),
            "version": price_snapshot["version"],
        },
        "sources": sources,
        "summaries": summaries,
        "cells": sorted(cells, key=lambda cell: (cell["arm_id"], cell["case"], cell["repeat"])),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
