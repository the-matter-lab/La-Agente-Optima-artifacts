"""Result extraction and reporting for direct arylation BO-MCP campaign."""

from __future__ import annotations

from typing import Any


def format_candidate(candidate: dict[str, Any]) -> str:
    """Format a candidate dict as a readable string."""
    return (
        f"base={candidate['base']}, "
        f"ligand={candidate['ligand']}, "
        f"solvent={candidate['solvent']}, "
        f"conc={candidate['concentration']}M, "
        f"temp={candidate['temperature_c']}°C"
    )


def extract_results_from_bo_mcp(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Extract standardized result records from BO-MCP result rows.

    Returns list of dicts with:
    - candidate: parameter dict
    - yield: objective value (float) or None
    - status: "success" or "failed" (all BO-MCP results are successes by definition)
    - result_id: BO-MCP result ID
    - suggestion_id: BO-MCP suggestion ID if available
    """
    extracted = []
    for row in results:
        param_vals = row.get("parameter_values", {})
        obj_vals = row.get("objective_values", {})
        yield_val = obj_vals.get("yield")

        # BO-MCP only stores successful submissions; failed evaluations
        # are tracked separately in the campaign script's local state
        extracted.append({
            "candidate": param_vals,
            "yield": float(yield_val) if yield_val is not None else None,
            "status": "success" if yield_val is not None else "failed",
            "result_id": row.get("result_id"),
            "suggestion_id": row.get("suggestion_id"),
        })
    return extracted


def compute_summary(evaluated: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute campaign summary statistics from all evaluated candidates.

    Args:
        evaluated: List of evaluation result dicts from evaluator.evaluate_batch
                   (includes both success and failed entries)

    Returns:
        Summary dict with best conditions, counts, etc.
    """
    successful = [r for r in evaluated if r["status"] == "success" and r["yield"] is not None]
    failed = [r for r in evaluated if r["status"] == "failed"]

    summary = {
        "total_attempted": len(evaluated),
        "successful_count": len(successful),
        "failed_count": len(failed),
        "best_yield": None,
        "best_candidate": None,
        "worst_yield": None,
        "worst_candidate": None,
        "mean_yield": None,
    }

    if successful:
        yields = [r["yield"] for r in successful]
        best_idx = yields.index(max(yields))
        worst_idx = yields.index(min(yields))
        summary.update({
            "best_yield": max(yields),
            "best_candidate": successful[best_idx]["candidate"],
            "worst_yield": min(yields),
            "worst_candidate": successful[worst_idx]["candidate"],
            "mean_yield": sum(yields) / len(yields),
        })

    return summary


def print_campaign_report(
    campaign_id: str,
    evaluated: list[dict[str, Any]],
    summary: dict[str, Any] | None = None,
) -> None:
    """Print a formatted campaign report to stdout."""
    if summary is None:
        summary = compute_summary(evaluated)

    print("\n" + "=" * 70)
    print(f"CAMPAIGN REPORT: {campaign_id}")
    print("=" * 70)
    print(f"Total attempted evaluations: {summary['total_attempted']}")
    print(f"Successful:                  {summary['successful_count']}")
    print(f"Failed:                      {summary['failed_count']}")

    if summary["best_yield"] is not None:
        print(f"\nBest yield: {summary['best_yield']:.2f}%")
        print(f"  Conditions: {format_candidate(summary['best_candidate'])}")
        print(f"Worst yield: {summary['worst_yield']:.2f}%")
        print(f"  Conditions: {format_candidate(summary['worst_candidate'])}")
        print(f"Mean yield: {summary['mean_yield']:.2f}%")

    print("\nAll evaluated candidates:")
    print("-" * 70)
    for i, r in enumerate(evaluated, 1):
        status_marker = "✓" if r["status"] == "success" else "✗"
        yield_str = f"{r['yield']:.2f}%" if r["yield"] is not None else "FAILED"
        error_str = f" ({r['error']})" if r["error"] else ""
        print(f"  {i:3d}. {status_marker} {yield_str:>8} | {format_candidate(r['candidate'])}{error_str}")

    print("=" * 70)


def print_final_summary_line(campaign_id: str, summary: dict[str, Any]) -> None:
    """Print the required final summary line with campaign ID."""
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}")