#!/usr/bin/env python3
"""Pairwise 2D projections of tested-point coverage for numeric search dimensions."""
from __future__ import annotations
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

from search_space_plot_utils import NUMERIC_PARAMS, load_points, stage_markers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=Path("plots/search_space_coverage"))
    ap.add_argument("--include-failed-tested", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()
    df, source = load_points(args.input, include_failed=args.include_failed_tested)
    args.outdir.mkdir(parents=True, exist_ok=True)

    n = len(NUMERIC_PARAMS)
    fig, axes = plt.subplots(n, n, figsize=(13, 12), constrained_layout=True)
    valid = df[df["valid_bo_result"].fillna(False)].copy()
    failed = df[~df["valid_bo_result"].fillna(False)].copy()
    norm = Normalize(vmin=float(valid["yield_percent"].min()), vmax=float(valid["yield_percent"].max()))
    cmap = plt.get_cmap("viridis")

    for i, yparam in enumerate(NUMERIC_PARAMS):
        for j, xparam in enumerate(NUMERIC_PARAMS):
            ax = axes[i, j]
            if i == j:
                ax.hist(valid[xparam].dropna(), bins=10, color="#9ecae1", edgecolor="white")
                ax.set_yticks([])
            else:
                ax.scatter(valid[xparam], valid[yparam], c=valid["yield_percent"], cmap=cmap, norm=norm, s=45, alpha=0.88, edgecolor="white", linewidth=0.4)
                if not failed.empty:
                    ax.scatter(failed[xparam], failed[yparam], marker="x", c="#777777", s=55, alpha=0.75, linewidth=1.2)
            if i == n - 1:
                ax.set_xlabel(xparam.replace("_", "\n"), fontsize=8)
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(yparam.replace("_", "\n"), fontsize=8)
            else:
                ax.set_yticklabels([])
            ax.grid(True, alpha=0.18)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=axes, shrink=0.7, pad=0.01)
    cbar.set_label("Yield (%)")
    fig.suptitle("Pairwise search-space coverage projections\nvalid points colored by yield; gray x = failed/unsubmitted tested attempts", fontsize=14)
    fig.text(0.01, 0.005, f"Source: {source}", fontsize=8, color="0.35")

    png = args.outdir / "search_space_pairwise_numeric.png"
    svg = args.outdir / "search_space_pairwise_numeric.svg"
    fig.savefig(png, dpi=220)
    fig.savefig(svg)
    print(f"Read {len(df)} tested/valid point rows from {source}")
    print(f"Wrote {png}\nWrote {svg}")

if __name__ == "__main__":
    main()
