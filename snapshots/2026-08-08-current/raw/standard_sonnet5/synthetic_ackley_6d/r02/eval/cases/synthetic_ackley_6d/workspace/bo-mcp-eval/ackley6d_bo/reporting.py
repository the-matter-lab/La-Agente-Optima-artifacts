"""Append-only results artifact + concise stdout reporting.

Rows are provenance only: the loop must never read these files back to
decide what to do next (BO-MCP's ``next_action`` owns that).
"""

import csv
import json
from pathlib import Path


def artifact_paths(artifact_dir: Path) -> tuple[Path, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir / "results.csv", artifact_dir / "results.jsonl"


def append_row(csv_path: Path, jsonl_path: Path, row: dict, param_names: list[str]) -> None:
    """Append one evaluated-candidate row to the CSV and JSONL artifacts."""
    header = (
        ["evaluation_index"]
        + param_names
        + ["surface_response", "raw_response", "status", "failure_reason"]
    )
    write_header = not csv_path.exists()
    flat = {
        "evaluation_index": row["evaluation_index"],
        **row["parameter_values"],
        "surface_response": row.get("surface_response"),
        "raw_response": row.get("raw_response"),
        "status": row["status"],
        "failure_reason": row.get("failure_reason"),
    }
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if write_header:
            writer.writeheader()
        writer.writerow(flat)
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(row) + "\n")


def summarize(rows: list[dict]) -> dict:
    """Compute best-so-far + counts from a list of row dicts (this-invocation rows)."""
    successes = [r for r in rows if r["status"] == "success"]
    best = max(successes, key=lambda r: r["surface_response"]) if successes else None
    return {
        "attempted": len(rows),
        "successful": len(successes),
        "best": best,
    }


def print_result_line(row: dict) -> None:
    coords = ", ".join(f"{k}={v:.4f}" for k, v in row["parameter_values"].items())
    if row["status"] == "success":
        print(
            f"[RESULT] eval={row['evaluation_index']} status=success "
            f"surface_response={row['surface_response']:.6f} "
            f"raw_response={row['raw_response']:.6f} ({coords})",
            flush=True,
        )
    else:
        print(
            f"[RESULT] eval={row['evaluation_index']} status=failed "
            f"reason={row.get('failure_reason')} ({coords})",
            flush=True,
        )


def print_final_summary(campaign_id: str, attempted: int, successful: int, best: dict | None) -> None:
    """Print the authoritative end-of-run summary.

    ``attempted``/``successful``/``best`` should be derived from BO-MCP
    server state (not local files) so the report is correct across resumed
    invocations too.
    """
    print("[EVENT] final summary", flush=True)
    print(f"BO_MCP_CAMPAIGN_ID={campaign_id}", flush=True)
    print(f"attempted_evaluations={attempted}", flush=True)
    print(f"successful_evaluations={successful}", flush=True)
    if best is None:
        print("best_result=none (no successful evaluations)", flush=True)
        return
    coords = ", ".join(f"{k}={v:.6f}" for k, v in best["parameter_values"].items())
    print(f"best_surface_response={best['surface_response']:.6f}", flush=True)
    print(f"best_raw_response={best['raw_response']:.6f}", flush=True)
    print(f"best_parameter_values={{{coords}}}", flush=True)

