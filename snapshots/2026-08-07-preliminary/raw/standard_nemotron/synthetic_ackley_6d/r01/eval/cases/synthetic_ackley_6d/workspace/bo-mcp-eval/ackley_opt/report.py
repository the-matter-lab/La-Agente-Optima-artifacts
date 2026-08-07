"""Reporting and artifact generation for Ackley 6D campaign."""

import csv
import json
from pathlib import Path
from typing import Any


def write_results_artifact(
    results: list[dict[str, Any]], artifact_path: Path
) -> None:
    """Write results artifact as JSONL (one row per evaluation)."""
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with artifact_path.open("w") as f:
        for i, r in enumerate(results):
            row = {
                "evaluation_index": i,
                "parameter_values": r.get("parameter_values", {}),
                "objective_values": r.get("objective_values", {}),
                "status": r.get("status", "unknown"),
                "failure_reason": r.get("failure_reason"),
                "raw_response": r.get("metadata", {}).get("raw_response"),
            }
            f.write(json.dumps(row) + "\n")


def write_results_csv(
    results: list[dict[str, Any]], csv_path: Path
) -> None:
    """Write results as CSV for easy viewing."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "evaluation_index",
        "x_1",
        "x_2",
        "x_3",
        "x_4",
        "x_5",
        "x_6",
        "surface_response",
        "raw_response",
        "status",
        "failure_reason",
    ]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(results):
            params = r.get("parameter_values", {})
            row = {
                "evaluation_index": i,
                "x_1": params.get("x_1"),
                "x_2": params.get("x_2"),
                "x_3": params.get("x_3"),
                "x_4": params.get("x_4"),
                "x_5": params.get("x_5"),
                "x_6": params.get("x_6"),
                "surface_response": r.get("objective_values", {}).get("surface_response"),
                "raw_response": r.get("metadata", {}).get("raw_response"),
                "status": r.get("status", "unknown"),
                "failure_reason": r.get("failure_reason", ""),
            }
            writer.writerow(row)


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics from results."""
    successful = [r for r in results if r.get("status") == "success"]
    failed = [r for r in results if r.get("status") == "failed"]
    duplicates = [r for r in results if r.get("status") == "duplicate"]

    best = None
    if successful:
        best = max(successful, key=lambda r: r.get("objective_values", {}).get("surface_response", -1))

    return {
        "total_attempted": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "duplicates": len(duplicates),
        "best_surface_response": best.get("objective_values", {}).get("surface_response") if best else None,
        "best_raw_response": best.get("metadata", {}).get("raw_response") if best else None,
        "best_coordinates": best.get("parameter_values") if best else None,
    }


def print_summary(summary: dict[str, Any]) -> None:
    """Print a formatted summary to stdout."""
    print("\n" + "=" * 60)
    print("ACKLEY 6D OPTIMIZATION SUMMARY")
    print("=" * 60)
    print(f"Total attempted evaluations: {summary['total_attempted']}")
    print(f"  Successful:                {summary['successful']}")
    print(f"  Failed:                    {summary['failed']}")
    print(f"  Duplicates:                {summary['duplicates']}")
    print("-" * 60)
    if summary["best_surface_response"] is not None:
        print(f"Best surface_response:       {summary['best_surface_response']:.6f}")
        raw = summary["best_raw_response"]
        if raw is not None:
            print(f"Best raw_response:           {raw:.6f}")
        else:
            print(f"Best raw_response:           N/A")
        coords = summary["best_coordinates"]
        if coords:
            coord_str = ", ".join(f"{k}={v:.6f}" for k, v in coords.items())
            print(f"Best coordinates:            {coord_str}")
    else:
        print("No successful evaluations.")
    print("=" * 60 + "\n")


def print_results_table(results: list[dict[str, Any]]) -> None:
    """Print a table of all evaluated candidates."""
    print("\nALL EVALUATED CANDIDATES")
    print("-" * 100)
    header = (
        f"{'Idx':>4}  {'x_1':>8} {'x_2':>8} {'x_3':>8} {'x_4':>8} {'x_5':>8} {'x_6':>8}  "
        f"{'surface':>10} {'raw':>10}  {'status':>10}"
    )
    print(header)
    print("-" * 100)
    for i, r in enumerate(results):
        params = r.get("parameter_values", {})
        coords = [params.get(f"x_{j}", 0.0) for j in range(1, 7)]
        surface = r.get("objective_values", {}).get("surface_response")
        raw = r.get("metadata", {}).get("raw_response")
        status = r.get("status", "unknown")
        coord_str = " ".join(f"{c:8.4f}" for c in coords)
        surf_str = f"{surface:10.6f}" if surface is not None else "    N/A   "
        raw_str = f"{raw:10.6f}" if raw is not None else "    N/A   "
        print(f"{i:4d}  {coord_str}  {surf_str} {raw_str}  {status:>10}")
    print("-" * 100 + "\n")