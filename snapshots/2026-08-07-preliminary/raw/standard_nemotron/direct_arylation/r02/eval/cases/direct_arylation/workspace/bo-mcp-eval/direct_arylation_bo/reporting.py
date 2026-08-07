"""Results reporting for the direct arylation campaign."""

import json
from pathlib import Path
from typing import Any


def format_candidate(candidate: dict[str, Any]) -> str:
    """Format a candidate for readable output."""
    parts = []
    for key in ["base", "ligand", "solvent", "concentration", "temperature_c"]:
        if key in candidate:
            val = candidate[key]
            if isinstance(val, float):
                parts.append(f"{key}={val:.3f}")
            else:
                parts.append(f"{key}={val}")
    return ", ".join(parts)


def generate_final_report(
    campaign_id: str,
    all_results: list[dict[str, Any]],
    artifacts_dir: Path,
) -> dict[str, Any]:
    """Generate the final campaign report.

    Args:
        campaign_id: BO-MCP campaign ID
        all_results: List of result dicts from evaluation (with status, yield, candidate, error)
        artifacts_dir: Directory to write artifact files

    Returns:
        Summary dictionary with key metrics
    """
    successful = [r for r in all_results if r["status"] == "success"]
    failed = [r for r in all_results if r["status"] == "failed"]

    if successful:
        best = max(successful, key=lambda r: r["yield"])
        best_yield = best["yield"]
        best_candidate = best["candidate"]
    else:
        best_yield = None
        best_candidate = None

    summary = {
        "campaign_id": campaign_id,
        "objective": "yield",
        "objective_direction": "maximize",
        "units": "percent",
        "total_attempted": len(all_results),
        "successful_evaluations": len(successful),
        "failed_evaluations": len(failed),
        "best_yield": best_yield,
        "best_conditions": best_candidate,
        "all_evaluations": all_results,
    }

    # Write summary JSON
    summary_path = artifacts_dir / "campaign_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # Write human-readable report
    report_path = artifacts_dir / "campaign_report.txt"
    with report_path.open("w") as f:
        f.write(f"Direct Arylation Yield Optimization Campaign Report\n")
        f.write(f"==================================================\n\n")
        f.write(f"Campaign ID: {campaign_id}\n")
        f.write(f"Objective: maximize yield (%)\n\n")
        f.write(f"Total attempted evaluations: {len(all_results)}\n")
        f.write(f"Successful evaluations: {len(successful)}\n")
        f.write(f"Failed evaluations: {len(failed)}\n\n")

        if best_yield is not None:
            f.write(f"Best yield: {best_yield:.2f}%\n")
            f.write(f"Best conditions:\n")
            for key, val in best_candidate.items():
                if isinstance(val, float):
                    f.write(f"  {key}: {val:.3f}\n")
                else:
                    f.write(f"  {key}: {val}\n")
        else:
            f.write("No successful evaluations.\n")

        f.write("\nAll evaluations:\n")
        for i, r in enumerate(all_results, 1):
            status = r["status"]
            candidate_str = format_candidate(r["candidate"])
            if status == "success":
                f.write(f"  {i}. [SUCCESS] yield={r['yield']:.2f}%  ({candidate_str})\n")
            else:
                f.write(f"  {i}. [FAILED]  error={r['error']}  ({candidate_str})\n")

    return summary


def print_final_summary(summary: dict[str, Any]) -> None:
    """Print the final summary to stdout with required format."""
    print("\n" + "=" * 60)
    print("CAMPAIGN COMPLETE")
    print("=" * 60)
    print(f"Campaign ID: {summary['campaign_id']}")
    print(f"Objective: {summary['objective']} ({summary['objective_direction']}, {summary['units']})")
    print(f"Total attempted: {summary['total_attempted']}")
    print(f"Successful: {summary['successful_evaluations']}")
    print(f"Failed: {summary['failed_evaluations']}")
    if summary['best_yield'] is not None:
        print(f"Best yield: {summary['best_yield']:.2f}%")
        print("Best conditions:")
        for key, val in summary['best_conditions'].items():
            if isinstance(val, float):
                print(f"  {key}: {val:.3f}")
            else:
                print(f"  {key}: {val}")
    else:
        print("Best yield: N/A (no successful evaluations)")
    print("=" * 60)
    # Required marker line for the user response
    print(f"BO_MCP_CAMPAIGN_ID={summary['campaign_id']}")