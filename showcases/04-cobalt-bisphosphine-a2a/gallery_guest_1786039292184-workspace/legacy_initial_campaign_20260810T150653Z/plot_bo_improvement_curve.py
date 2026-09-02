#!/usr/bin/env python3
"""Plot a multi-objective BO improvement curve from a BO-MCP campaign export.

For this Hood-inspired Co bisphosphine campaign the objectives are:
  - electronic_activation: maximize
  - coordination_stability: maximize
  - chelate_geometry: maximize
  - steric_crowding: minimize

The script converts all objectives to maximization by using -steric_crowding,
then plots the cumulative dominated hypervolume after each submitted result.
The first N rows can be marked as warm-start observations; the rest are BO-
selected observations.
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

# Use a non-interactive backend so the script works in headless containers.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MAX_OBJECTIVES = [
    "obj_electronic_activation",
    "obj_coordination_stability",
    "obj_chelate_geometry",
]
MIN_OBJECTIVES = ["obj_steric_crowding"]
ALL_OBJECTIVES = MAX_OBJECTIVES + MIN_OBJECTIVES


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        default="hood_co_bisphosphine_artifacts_restart3/campaign_export.csv",
        help="BO-MCP campaign export CSV.",
    )
    p.add_argument(
        "--output",
        default="hood_co_bisphosphine_artifacts_restart3/bo_improvement_curve.png",
        help="Output figure path.",
    )
    p.add_argument(
        "--summary-csv",
        default="hood_co_bisphosphine_artifacts_restart3/bo_improvement_curve_summary.csv",
        help="Output per-iteration summary CSV.",
    )
    p.add_argument(
        "--warm-start-count",
        type=int,
        default=4,
        help="Number of initial rows to mark as warm-start observations.",
    )
    p.add_argument(
        "--title",
        default="Hood-inspired Co(II) bisphosphine BO improvement",
        help="Figure title.",
    )
    return p.parse_args()


def load_campaign_export(path: Path, warm_start_count: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.sort_values("created_at", kind="stable").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    missing = [c for c in ["param_candidate_id", *ALL_OBJECTIVES] if c not in df.columns]
    if missing:
        raise ValueError(f"Input CSV missing required columns: {missing}")

    for c in ALL_OBJECTIVES:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[ALL_OBJECTIVES].isna().any().any():
        bad = df[df[ALL_OBJECTIVES].isna().any(axis=1)]
        raise ValueError(f"Found nonnumeric objective values in rows: {bad.index.tolist()}")

    df["iteration"] = np.arange(1, len(df) + 1)
    df["phase"] = np.where(df["iteration"] <= warm_start_count, "warm-start", "BO")
    # In this campaign hard-penalized infeasible points have large negative max objectives
    # and large positive steric crowding. This heuristic is for plotting markers only.
    df["feasible_like"] = ~(
        (df["obj_electronic_activation"] <= -99)
        & (df["obj_coordination_stability"] <= -99)
        & (df["obj_chelate_geometry"] <= -99)
        & (df["obj_steric_crowding"] >= 99)
    )
    return df


def to_maximization_matrix(df: pd.DataFrame) -> np.ndarray:
    """Return objective matrix where every column is to be maximized."""
    return np.column_stack(
        [
            df["obj_electronic_activation"].to_numpy(float),
            df["obj_coordination_stability"].to_numpy(float),
            df["obj_chelate_geometry"].to_numpy(float),
            -df["obj_steric_crowding"].to_numpy(float),
        ]
    )


def pareto_mask_max(points: np.ndarray) -> np.ndarray:
    """Nondominated mask for maximization objectives."""
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        # j dominates i if j >= i in all objectives and > in at least one.
        dominates_i = np.all(points >= points[i], axis=1) & np.any(points > points[i], axis=1)
        if np.any(dominates_i):
            keep[i] = False
    return keep


def hypervolume_inclusion_exclusion(points: np.ndarray, reference: np.ndarray) -> float:
    """Exact dominated hypervolume for small non-dominated maximization sets.

    Computes the union volume of axis-aligned boxes [reference, point]. This
    inclusion-exclusion implementation is fine for the small campaign sizes here.
    """
    if len(points) == 0:
        return 0.0
    # Keep only points that dominate the reference in every dimension.
    pts = points[np.all(points > reference, axis=1)]
    if len(pts) == 0:
        return 0.0
    pts = pts[pareto_mask_max(pts)]

    hv = 0.0
    n = len(pts)
    for k in range(1, n + 1):
        sign = 1.0 if k % 2 else -1.0
        for combo in itertools.combinations(range(n), k):
            upper = np.min(pts[list(combo)], axis=0)
            widths = np.maximum(upper - reference, 0.0)
            hv += sign * float(np.prod(widths))
    # Numeric noise can make a nearly-zero value slightly negative.
    return max(hv, 0.0)


def add_hypervolume_columns(df: pd.DataFrame) -> pd.DataFrame:
    y = to_maximization_matrix(df)
    # Use a fixed reference point one unit worse than the observed worst value in
    # each transformed objective. This includes hard-penalized failures but gives
    # them very little volume relative to successful points.
    reference = np.min(y, axis=0) - 1.0

    hvs = []
    pareto_sizes = []
    best_scalar = []

    # A simple normalized utility is useful as a visual companion to HV. It is not
    # the BO objective; it is only a plotting aid.
    ideal = np.max(y, axis=0)
    denom = np.where(ideal > reference, ideal - reference, 1.0)
    yn = (y - reference) / denom

    for i in range(1, len(df) + 1):
        pts = y[:i]
        hvs.append(hypervolume_inclusion_exclusion(pts, reference))
        pareto_sizes.append(int(pareto_mask_max(pts).sum()))
        # Equal-weight utility in transformed/maximized objective space.
        best_scalar.append(float(np.max(np.mean(yn[:i], axis=1))))

    out = df.copy()
    out["hypervolume"] = hvs
    final_hv = hvs[-1] if hvs and hvs[-1] > 0 else 1.0
    out["hypervolume_normalized_to_final"] = np.array(hvs) / final_hv
    out["pareto_set_size_so_far"] = pareto_sizes
    out["best_equal_weight_normalized_utility_so_far"] = best_scalar
    out.attrs["reference_point_max_space"] = reference.tolist()
    return out


def plot(df: pd.DataFrame, output: Path, title: str, warm_start_count: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    ax = axes[0]
    ax2 = axes[1]

    x = df["iteration"].to_numpy()
    hv = df["hypervolume_normalized_to_final"].to_numpy()

    ax.plot(x, hv, color="#1f77b4", lw=2.5, marker="o", label="Cumulative hypervolume")
    # Overlay marker shape/color by phase/feasibility.
    for phase, marker, color in [("warm-start", "s", "#ff7f0e"), ("BO", "o", "#2ca02c")]:
        sub = df[df["phase"] == phase]
        ax.scatter(
            sub["iteration"],
            sub["hypervolume_normalized_to_final"],
            s=70,
            marker=marker,
            color=color,
            edgecolor="black",
            linewidth=0.6,
            label=phase,
            zorder=3,
        )
    failed = df[~df["feasible_like"]]
    if not failed.empty:
        ax.scatter(
            failed["iteration"],
            failed["hypervolume_normalized_to_final"],
            s=130,
            marker="x",
            color="red",
            linewidth=2.0,
            label="hard-penalized / infeasible",
            zorder=4,
        )

    if warm_start_count and warm_start_count < len(df):
        ax.axvline(warm_start_count + 0.5, color="0.35", ls="--", lw=1.5)
        ax.text(
            warm_start_count + 0.55,
            0.03,
            "BO takes over",
            rotation=90,
            va="bottom",
            ha="left",
            color="0.25",
        )

    ax.set_ylabel("Normalized cumulative hypervolume")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)

    # Lower panel: per-candidate steric crowding and cumulative best scalar utility.
    feasible_colors = np.where(df["feasible_like"], "#4c78a8", "#e45756")
    ax2.bar(x, df["obj_steric_crowding"], color=feasible_colors, alpha=0.75, label="Steric crowding (minimize)")
    ax2.set_ylabel("Steric crowding")
    ax2.set_xlabel("Evaluation number")
    ax2.grid(True, axis="y", alpha=0.3)

    ax2b = ax2.twinx()
    ax2b.plot(
        x,
        df["best_equal_weight_normalized_utility_so_far"],
        color="black",
        lw=2,
        marker=".",
        label="Best equal-weight normalized utility",
    )
    ax2b.set_ylabel("Best normalized utility")
    ax2b.set_ylim(0, 1.05)

    # Candidate labels, shortened for readability.
    labels = df["param_candidate_id"].astype(str).tolist()
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)

    # Combined legend for lower panel.
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)

    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.30, hspace=0.12)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    summary = Path(args.summary_csv)

    df = load_campaign_export(inp, args.warm_start_count)
    df = add_hypervolume_columns(df)
    summary.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(summary, index=False)
    plot(df, out, args.title, args.warm_start_count)

    print(f"Wrote figure: {out}")
    print(f"Wrote summary: {summary}")
    print(f"Rows: {len(df)}")
    print(f"Feasible-like rows: {int(df['feasible_like'].sum())}/{len(df)}")
    print(f"Final normalized hypervolume: {df['hypervolume_normalized_to_final'].iloc[-1]:.3f}")
    print(f"Final Pareto set size estimate: {int(df['pareto_set_size_so_far'].iloc[-1])}")
    print(f"Reference point in maximization space: {df.attrs['reference_point_max_space']}")


if __name__ == "__main__":
    main()
