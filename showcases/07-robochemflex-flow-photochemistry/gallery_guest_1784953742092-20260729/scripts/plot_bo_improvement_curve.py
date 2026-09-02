#!/usr/bin/env python3
"""Plot BO improvement curve for the RoboChemFlex yield campaign.

The script reads a BO-MCP campaign export CSV (or auto-discovers the most
complete/latest export in artifacts/) and plots:
  1. per-experiment yield and cumulative best yield;
  2. per-experiment scalarized desirability and cumulative best desirability.

It does not hard-code campaign results. The only default campaign assumption is
that the first 6 rows are informed seed experiments; override with --seed-count.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DEFAULT_SEARCH_ROOT = Path("artifacts/recreated_robochemflex_yield_bo_20260725")
DEFAULT_OUTDIR = Path("plots")


def discover_export(search_root: Path = DEFAULT_SEARCH_ROOT) -> Path:
    candidates = list(search_root.rglob("bo_campaign_export.csv"))
    if not candidates:
        raise FileNotFoundError(f"No bo_campaign_export.csv found under {search_root}")

    def score(path: Path) -> tuple[int, float]:
        try:
            nrows = len(pd.read_csv(path))
        except Exception:
            nrows = -1
        return (nrows, path.stat().st_mtime)

    return max(candidates, key=score)


def desirability(yield_percent: pd.Series, green_score: pd.Series, yield_weight: float, green_weight: float) -> pd.Series:
    """Weighted geometric desirability on [0, 1]."""
    y = (yield_percent.astype(float).clip(0, 100) / 100.0).clip(lower=0)
    g = (green_score.astype(float).clip(0, 100) / 100.0).clip(lower=0)
    # If yield is zero, desirability is exactly zero for the geometric mean.
    return (y ** yield_weight) * (g ** green_weight)


def load_export(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"obj_yield_percent", "obj_green_score"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required column(s): {sorted(missing)}")
    df = df.copy()
    df["experiment"] = np.arange(1, len(df) + 1)
    df["yield_percent"] = pd.to_numeric(df["obj_yield_percent"], errors="raise")
    df["green_score"] = pd.to_numeric(df["obj_green_score"], errors="raise")
    return df


def plot(df: pd.DataFrame, source: Path, outdir: Path, seed_count: int, yield_weight: float, green_weight: float) -> tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["desirability"] = desirability(df["yield_percent"], df["green_score"], yield_weight, green_weight)
    df["cum_best_yield"] = df["yield_percent"].cummax()
    df["cum_best_desirability"] = df["desirability"].cummax()
    df["phase"] = np.where(df["experiment"] <= seed_count, "seed", "BO")

    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.0), sharex=True, constrained_layout=True)
    seed_color = "#4C78A8"
    bo_color = "#F58518"
    best_color = "#222222"

    # Background regions
    for ax in axes:
        ax.axvspan(0.5, seed_count + 0.5, color=seed_color, alpha=0.08, label="seed region" if ax is axes[0] else None)
        if len(df) > seed_count:
            ax.axvspan(seed_count + 0.5, len(df) + 0.5, color=bo_color, alpha=0.06, label="BO region" if ax is axes[0] else None)
        ax.axvline(seed_count + 0.5, color="0.55", linestyle="--", linewidth=1)
        ax.grid(True, alpha=0.25)

    # Panel 1: yield improvement
    ax = axes[0]
    seed = df[df["phase"] == "seed"]
    bo = df[df["phase"] == "BO"]
    ax.scatter(seed["experiment"], seed["yield_percent"], s=55, color=seed_color, edgecolor="white", linewidth=0.7, label="seed experiments")
    ax.scatter(bo["experiment"], bo["yield_percent"], s=55, color=bo_color, edgecolor="white", linewidth=0.7, label="BO-selected experiments")
    ax.step(df["experiment"], df["cum_best_yield"], where="post", color=best_color, linewidth=2.3, label="cumulative best yield")
    best_idx = int(df["yield_percent"].idxmax())
    ax.scatter([df.loc[best_idx, "experiment"]], [df.loc[best_idx, "yield_percent"]], s=130, marker="*", color="#54A24B", edgecolor="black", linewidth=0.6, zorder=5, label="best yield")
    ax.set_ylabel("Yield (%)")
    ax.set_title("BO improvement curve over 20 RoboFlex experiments")
    ax.legend(loc="upper left", ncol=2, fontsize=9)

    # Panel 2: scalarized desirability improvement
    ax = axes[1]
    ax.scatter(seed["experiment"], seed["desirability"], s=55, color=seed_color, edgecolor="white", linewidth=0.7, label="seed experiments")
    ax.scatter(bo["experiment"], bo["desirability"], s=55, color=bo_color, edgecolor="white", linewidth=0.7, label="BO-selected experiments")
    ax.step(df["experiment"], df["cum_best_desirability"], where="post", color=best_color, linewidth=2.3, label="cumulative best desirability")
    best_s_idx = int(df["desirability"].idxmax())
    ax.scatter([df.loc[best_s_idx, "experiment"]], [df.loc[best_s_idx, "desirability"]], s=130, marker="*", color="#54A24B", edgecolor="black", linewidth=0.6, zorder=5, label="best desirability")
    ax.set_xlabel("Experiment number")
    ax.set_ylabel(f"Desirability\n(yield^{yield_weight:g} × green^{green_weight:g})")
    ax.set_xlim(0.5, len(df) + 0.5)
    ax.set_xticks(df["experiment"])
    ax.legend(loc="upper left", ncol=2, fontsize=9)

    # Footnote/source
    fig.text(0.01, 0.005, f"Source: {source} | first {seed_count} experiments marked as seeds", fontsize=8, color="0.35")

    png = outdir / "bo_improvement_curve.png"
    svg = outdir / "bo_improvement_curve.svg"
    data = outdir / "bo_improvement_curve_data.csv"
    fig.savefig(png, dpi=220)
    fig.savefig(svg)
    df.to_csv(data, index=False)
    return png, svg, data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None, help="BO-MCP export CSV. Auto-discovered if omitted.")
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--seed-count", type=int, default=6)
    parser.add_argument("--yield-weight", type=float, default=0.8)
    parser.add_argument("--green-weight", type=float, default=0.2)
    args = parser.parse_args()

    source = args.input or discover_export(args.search_root)
    df = load_export(source)
    png, svg, data = plot(df, source, args.outdir, args.seed_count, args.yield_weight, args.green_weight)
    print(f"Read {len(df)} experiments from {source}")
    print(f"Wrote {png}")
    print(f"Wrote {svg}")
    print(f"Wrote {data}")


if __name__ == "__main__":
    main()
