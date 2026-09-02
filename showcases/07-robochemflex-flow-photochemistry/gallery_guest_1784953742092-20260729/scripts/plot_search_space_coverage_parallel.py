#!/usr/bin/env python3
"""Parallel-coordinate coverage plot for the mixed RoboChemFlex search space."""
from __future__ import annotations
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import Normalize

from search_space_plot_utils import PARAMS, load_intake, load_points, normalize_param, parameter_specs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=None, help="BO export CSV; auto-discovered if omitted")
    ap.add_argument("--intake", type=Path, default=None, help="Campaign intake JSON for parameter bounds/categories")
    ap.add_argument("--outdir", type=Path, default=Path("plots/search_space_coverage"))
    ap.add_argument("--include-failed-tested", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    df, source = load_points(args.input, include_failed=args.include_failed_tested)
    specs = parameter_specs(load_intake(args.intake))
    args.outdir.mkdir(parents=True, exist_ok=True)

    normed = []
    ticks_by_axis = []
    for p in PARAMS:
        vals, ticks = normalize_param(df[p], specs[p])
        normed.append(vals)
        ticks_by_axis.append(ticks)

    x = np.arange(len(PARAMS))
    fig, ax = plt.subplots(figsize=(13.5, 7.5), constrained_layout=True)
    cmap = plt.get_cmap("viridis")
    valid_yields = df.loc[df["valid_bo_result"].fillna(False), "yield_percent"].dropna()
    norm = Normalize(vmin=float(valid_yields.min()), vmax=float(valid_yields.max()))

    # Draw failed attempts first, then valid low-to-high yield so high-yield lines sit on top.
    order = df.assign(_valid=df["valid_bo_result"].fillna(False), _yield=df["yield_percent"].fillna(-1)).sort_values(["_valid", "_yield"]).index
    for idx in order:
        y = [arr.iloc[idx] for arr in normed]
        if any(v != v for v in y):
            continue
        row = df.iloc[idx]
        if bool(row.get("valid_bo_result")):
            color = cmap(norm(row["yield_percent"]))
            lw = 1.2 + 1.8 * norm(row["yield_percent"])
            alpha = 0.55 if row.get("stage") != "yield-only BO" else 0.95
            ls = "-"
        else:
            color = "#777777"
            lw = 1.1
            alpha = 0.35
            ls = "--"
        ax.plot(x, y, color=color, alpha=alpha, linewidth=lw, linestyle=ls)

    ax.set_xlim(x[0], x[-1])
    ax.set_ylim(-0.04, 1.04)
    ax.set_xticks(x)
    ax.set_xticklabels([p.replace("_", "\n") for p in PARAMS], fontsize=10)
    ax.set_yticks([])
    ax.set_title("Tested-point coverage of the RoboChemFlex search space\nparallel coordinates; color = yield for valid BO results")
    ax.grid(axis="x", alpha=0.25)

    # Axis-specific tick labels as small text next to each vertical axis.
    for xi, ticks in enumerate(ticks_by_axis):
        ax.axvline(xi, color="0.75", lw=0.8, zorder=0)
        for val, lab in ticks:
            ax.text(xi + 0.03, val, lab, fontsize=7, va="center", color="0.25")

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, pad=0.01)
    cbar.set_label("Yield (%)")
    ax.text(0.01, 0.01, f"Source: {source}\nDashed gray lines = failed/unsubmitted tested attempts when present", transform=ax.transAxes, fontsize=8, color="0.35", va="bottom")

    png = args.outdir / "search_space_parallel_coordinates.png"
    svg = args.outdir / "search_space_parallel_coordinates.svg"
    data = args.outdir / "search_space_coverage_points.csv"
    fig.savefig(png, dpi=220)
    fig.savefig(svg)
    df.to_csv(data, index=False)
    print(f"Read {len(df)} tested/valid point rows from {source}")
    print(f"Wrote {png}\nWrote {svg}\nWrote {data}")

if __name__ == "__main__":
    main()
