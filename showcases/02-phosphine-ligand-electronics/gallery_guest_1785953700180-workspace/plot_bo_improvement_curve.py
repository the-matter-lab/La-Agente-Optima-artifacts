#!/usr/bin/env python3
"""Plot BO improvement curves from phosphine campaign artifacts.

This script intentionally reads campaign data from artifact/export files rather
than embedding campaign results in code. By default it uses
campaign_manifest.json -> latest_artifact_dir, then reads evaluation_records.jsonl.

Outputs:
  - bo_improvement_curve.png
  - bo_improvement_curve.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OBJECTIVE_KEYS = ["donor_homo_error", "gap_error", "steric_excess", "heavy_atom_count"]


def default_artifact_dir() -> Path:
    manifest = Path("campaign_manifest.json")
    if manifest.exists():
        data = json.loads(manifest.read_text())
        latest = data.get("latest_artifact_dir")
        if latest and Path(latest).exists():
            return Path(latest)
    candidates = sorted(Path("artifacts").glob("phosphine_electronics_*"))
    if not candidates:
        raise FileNotFoundError("No phosphine_electronics artifact directory found")
    return candidates[-1]


def load_records(artifact_dir: Path) -> pd.DataFrame:
    records_path = artifact_dir / "evaluation_records.jsonl"
    if not records_path.exists():
        raise FileNotFoundError(f"Missing {records_path}")
    rows = []
    with records_path.open() as handle:
        for seq, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            rec = json.loads(line)
            obj = rec.get("objectives") or {}
            desc = rec.get("descriptors") or {}
            row = {
                "eval_index": seq,
                "candidate_id": rec.get("candidate_id"),
                "phase": rec.get("phase"),
                "status": rec.get("status"),
                "timestamp": rec.get("timestamp"),
                "homo_energy_eV": desc.get("homo_energy_eV"),
                "homo_lumo_gap_eV": desc.get("homo_lumo_gap_eV"),
                "molecular_volume_ang3": desc.get("molecular_volume_ang3"),
                "phosphorus_partial_charge": desc.get("phosphorus_partial_charge"),
            }
            for key in OBJECTIVE_KEYS:
                row[key] = obj.get(key)
            rows.append(row)
    df = pd.DataFrame(rows)
    ok = df["status"].eq("success") if "status" in df else pd.Series(False, index=df.index)
    return df.loc[ok].reset_index(drop=True)


def is_nondominated(points: np.ndarray) -> np.ndarray:
    """Return True for minimization nondominated rows."""
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        dominated_by_any = np.any(
            np.all(points <= points[i], axis=1) & np.any(points < points[i], axis=1)
        )
        if dominated_by_any:
            keep[i] = False
    return keep


def normalize_objectives(values: np.ndarray) -> np.ndarray:
    """Normalize minimization objectives with scales derived from observed data."""
    mins = np.nanmin(values, axis=0)
    maxs = np.nanmax(values, axis=0)
    span = maxs - mins
    # Degenerate objectives carry no observed discrimination; map them to zero
    # and keep the reference point finite.
    safe_span = np.where(span > 0, span, 1.0)
    return (values - mins) / safe_span


def hypervolume_min_2plus(points: np.ndarray, ref: np.ndarray) -> float:
    """Exact dominated hypervolume for small minimization fronts.

    Inclusion-exclusion over boxes [point, ref]. The campaign is small, so this
    transparent implementation is adequate and avoids adding a dependency.
    """
    if len(points) == 0:
        return 0.0
    nd = points[is_nondominated(points)]
    total = 0.0
    m = len(nd)
    # Inclusion-exclusion over all non-empty subsets of nondominated boxes.
    # For this campaign the Pareto-front size is small; if it grows much larger,
    # replace with a dedicated hypervolume library.
    for mask in range(1, 1 << m):
        subset_idx = [i for i in range(m) if (mask >> i) & 1]
        lower = np.max(nd[subset_idx], axis=0)
        widths = ref - lower
        vol = float(np.prod(np.clip(widths, 0.0, None)))
        if len(subset_idx) % 2:
            total += vol
        else:
            total -= vol
    return max(total, 0.0)


def cumulative_metrics(df: pd.DataFrame) -> pd.DataFrame:
    values = df[OBJECTIVE_KEYS].astype(float).to_numpy()
    norm = normalize_objectives(values)
    ref = np.nanmax(norm, axis=0) + 0.10  # data-derived normalized margin
    rows = []
    for i in range(1, len(df) + 1):
        current = values[:i]
        current_norm = norm[:i]
        nd_mask = is_nondominated(current)
        rows.append({
            "eval_index": int(df.loc[i - 1, "eval_index"]),
            "successful_eval_count": i,
            "latest_candidate_id": df.loc[i - 1, "candidate_id"],
            "latest_phase": df.loc[i - 1, "phase"],
            "cumulative_pareto_count": int(nd_mask.sum()),
            "normalized_hypervolume": hypervolume_min_2plus(current_norm, ref),
            "best_donor_homo_error": float(np.min(current[:, 0])),
            "best_gap_error": float(np.min(current[:, 1])),
            "best_heavy_atom_count": float(np.min(current[:, 3])),
        })
    out = pd.DataFrame(rows)
    first_bo = df.index[df["phase"].eq("bo")]
    out.attrs["first_bo_success_count"] = int(first_bo[0] + 1) if len(first_bo) else None
    return out


def plot_curve(metrics: pd.DataFrame, artifact_dir: Path) -> Path:
    first_bo = metrics.attrs.get("first_bo_success_count")
    fig, ax1 = plt.subplots(figsize=(10.5, 6.2), dpi=180)

    warm = metrics[metrics["latest_phase"].eq("warm_start")]
    bo = metrics[metrics["latest_phase"].eq("bo")]
    if not warm.empty:
        ax1.plot(warm["successful_eval_count"], warm["normalized_hypervolume"],
                 color="#7f7f7f", marker="o", lw=2, label="Warm-start accumulation")
    if not bo.empty:
        # Include the point immediately before BO for continuity.
        start_idx = max(int(bo.index.min()) - 1, 0)
        bo_line = metrics.loc[start_idx:]
        ax1.plot(bo_line["successful_eval_count"], bo_line["normalized_hypervolume"],
                 color="#1f77b4", marker="^", lw=2.2, label="BO-guided accumulation")

    if first_bo:
        ax1.axvline(first_bo - 0.5, color="black", ls="--", lw=1, alpha=0.65)
        ax1.text(first_bo - 0.45, ax1.get_ylim()[1], " BO starts", va="top", ha="left", fontsize=9)

    ax1.set_xlabel("Successful ligand evaluations, in artifact order")
    ax1.set_ylabel("Cumulative normalized dominated hypervolume\n(higher is better; objectives minimized)")
    ax1.grid(True, alpha=0.25)

    ax2 = ax1.twinx()
    ax2.step(metrics["successful_eval_count"], metrics["cumulative_pareto_count"],
             where="post", color="#d62728", lw=1.8, alpha=0.85, label="Cumulative Pareto-front size")
    ax2.set_ylabel("Cumulative Pareto-front size")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="lower right", framealpha=0.95)

    title = "BO improvement curve from phosphine campaign evaluation records"
    ax1.set_title(title)
    ax1.text(0.01, 0.99,
             "Hypervolume computed from the four recorded minimization objectives:\n"
             + ", ".join(OBJECTIVE_KEYS),
             transform=ax1.transAxes, va="top", ha="left", fontsize=8.5,
             bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.8", alpha=0.86))

    fig.tight_layout()
    out = artifact_dir / "bo_improvement_curve.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=None,
                        help="Campaign artifact directory; defaults to campaign_manifest.json latest_artifact_dir")
    args = parser.parse_args()
    artifact_dir = args.artifact_dir or default_artifact_dir()
    df = load_records(artifact_dir)
    if df.empty:
        raise SystemExit(f"No successful evaluations found in {artifact_dir}")
    metrics = cumulative_metrics(df)
    csv_out = artifact_dir / "bo_improvement_curve.csv"
    metrics.to_csv(csv_out, index=False)
    png_out = plot_curve(metrics, artifact_dir)
    print(f"Wrote {png_out}")
    print(f"Wrote {csv_out}")


if __name__ == "__main__":
    main()
