#!/usr/bin/env python3
"""Plot yield improvement for successful/submitted measurements only.

Reads a BO-MCP campaign export CSV (default: latest clean yield-only export)
and plots per-measurement yield plus cumulative best yield. Failed/unsubmitted
RoboFlex attempts are not included because they are not present in the BO export.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update(
    {
        "svg.fonttype": "none",
        "font.family": "Roboto Condensed",
        "font.size": 5,
        "axes.labelsize": 7,
        "axes.titlesize": 7,
        "xtick.labelsize": 5,
        "ytick.labelsize": 5,
        "axes.linewidth": 0.4,
        "axes.labelpad": 1.5,
        "axes.titlepad": 3,
        "xtick.major.width": 0.4,
        "ytick.major.width": 0.4,
        "xtick.major.size": 1.5,
        "ytick.major.size": 1.5,
        "xtick.major.pad": 1.5,
        "ytick.major.pad": 1.5,
        "legend.fontsize": 5,
    }
)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CM = 1 / 2.54
DEFAULT_SEARCH_ROOTS = [Path("artifacts"), Path("artifacts/yield_only_clean21_export_20260729T212630Z")]


def discover_export() -> Path:
    candidates = []
    for root in DEFAULT_SEARCH_ROOTS:
        if root.exists():
            candidates.extend(root.rglob("bo_campaign_export.csv") if root.is_dir() else [])
    # Prefer clean yield-only exports over older/superseded exports.
    candidates = [p for p in candidates if "clean21" in str(p) or "yield_only" in str(p)] or candidates
    if not candidates:
        raise FileNotFoundError("No bo_campaign_export.csv found under artifacts/")
    def score(p: Path) -> tuple[int, float]:
        try:
            n = len(pd.read_csv(p))
        except Exception:
            n = -1
        return (n, p.stat().st_mtime)
    return max(candidates, key=score)


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "obj_yield_percent" not in df.columns:
        raise ValueError(f"{path} missing obj_yield_percent")
    df = df.copy()
    df["experiment"] = np.arange(1, len(df) + 1)
    df["yield_percent"] = pd.to_numeric(df["obj_yield_percent"], errors="raise")
    df["cum_best_yield"] = df["yield_percent"].cummax()
    return df


def plot(df: pd.DataFrame, source: Path, outdir: Path, seed_count: int, yield_only_start: int) -> tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["stage"] = np.select(
        [df["experiment"] <= seed_count, df["experiment"] < yield_only_start],
        ["seed", "mixed-objective BO"],
        default="yield-only BO",
    )
    colors = {"seed": "#4C78A8", "mixed-objective BO": "#F58518", "yield-only BO": "#54A24B"}
    markers = {"seed": "o", "mixed-objective BO": "o", "yield-only BO": "D"}

    fig, ax = plt.subplots(figsize=(8 * CM, 6 * CM), dpi=600)
    xmax = int(df["experiment"].max())
    # Background regions.
    ax.axvspan(0.5, seed_count + 0.5, color=colors["seed"], alpha=0.08, linewidth=0)
    ax.axvspan(seed_count + 0.5, yield_only_start - 0.5, color=colors["mixed-objective BO"], alpha=0.06, linewidth=0)
    ax.axvspan(yield_only_start - 0.5, xmax + 0.5, color=colors["yield-only BO"], alpha=0.07, linewidth=0)
    ax.axvline(seed_count + 0.5, color="gray", linestyle="--", lw=0.6)
    ax.axvline(yield_only_start - 0.5, color="gray", linestyle="--", lw=0.6)

    for stage, sub in df.groupby("stage", sort=False):
        ax.scatter(sub["experiment"], sub["yield_percent"], s=10, color=colors[stage], marker=markers[stage], edgecolor="white", linewidth=0.35, label=stage, zorder=3)
    ax.step(df["experiment"], df["cum_best_yield"], where="post", color="#222222", lw=0.9, label="cumulative best yield", zorder=2)

    best_idx = int(df["yield_percent"].idxmax())
    ax.scatter([df.loc[best_idx, "experiment"]], [df.loc[best_idx, "yield_percent"]], s=30, marker="*", color="#D62728", edgecolor="black", linewidth=0.35, label="best yield", zorder=5)
    ax.annotate(
        f"best: exp {int(df.loc[best_idx, 'experiment'])}\n{df.loc[best_idx, 'yield_percent']:.2f}%",
        (df.loc[best_idx, "experiment"], df.loc[best_idx, "yield_percent"]),
        xytext=(-4, -4), textcoords="offset points", fontsize=5, ha="right", va="top",
    )

    ax.set_xlabel("# BO iteration")
    ax.set_ylabel("yield (%)")
    ax.set_xlim(0.5, xmax + 0.5)
    if xmax <= 16:
        tick_steps = list(range(1, xmax + 1))
    else:
        tick_steps = sorted(set([1, 4, 8, 12, 16] + list(range(20, xmax + 1, 4)) + [xmax]))
    ax.set_xticks(tick_steps)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", ncol=2, frameon=False, handlelength=1.5, columnspacing=0.8)
    plt.tight_layout(pad=0.3)

    png = outdir / "yield_only_successful_improvement_curve.png"
    svg = outdir / "yield_only_successful_improvement_curve.svg"
    data = outdir / "yield_only_successful_improvement_curve_data.csv"
    fig.savefig(png, transparent=True)
    fig.savefig(svg, transparent=True)
    plt.close(fig)
    df.to_csv(data, index=False)
    return png, svg, data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=Path("plots/yield_only_clean"))
    ap.add_argument("--seed-count", type=int, default=6)
    ap.add_argument("--yield-only-start", type=int, default=21, help="Measurement number where yield-only phase begins in the clean campaign")
    ap.add_argument("--exclude-experiments", type=str, default="", help="Comma-separated successful-measurement numbers to omit from the plot, e.g. 24,25,26")
    args = ap.parse_args()
    source = args.input or discover_export()
    df = load(source)
    excluded = []
    if args.exclude_experiments.strip():
        excluded = [int(x.strip()) for x in args.exclude_experiments.split(",") if x.strip()]
        df = df[~df["experiment"].isin(excluded)].copy()
        # Keep original measurement numbers; recompute cumulative best over displayed sequence.
        df["cum_best_yield"] = df["yield_percent"].cummax()
    png, svg, data = plot(df, source, args.outdir, args.seed_count, args.yield_only_start)
    print(f"Read {len(df)} successful/submitted measurements from {source}")
    if excluded:
        print(f"Excluded measurement numbers: {excluded}")
    print(f"Wrote {png}\nWrote {svg}\nWrote {data}")

if __name__ == "__main__":
    main()
