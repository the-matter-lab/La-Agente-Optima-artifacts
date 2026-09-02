#!/usr/bin/env python3
"""Chemically focused coverage map: residence time vs TFAA, with catalyst loading/lighting encoded."""
from __future__ import annotations
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

from search_space_plot_utils import load_points

MARKERS_BY_LIGHT = {0: "X", 25: "v", 50: "o", 75: "s", 100: "^"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=Path("plots/search_space_coverage"))
    ap.add_argument("--include-failed-tested", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--filter-main-region", action=argparse.BooleanOptionalAction, default=False, help="Filter to Ru bpy Cl / py NO only")
    args = ap.parse_args()
    df, source = load_points(args.input, include_failed=args.include_failed_tested)
    if args.filter_main_region:
        df = df[(df["catalyst_type"] == "Ru bpy Cl") & (df["oxidant_type"] == "py NO")].copy()
    args.outdir.mkdir(parents=True, exist_ok=True)

    valid = df[df["valid_bo_result"].fillna(False)].copy()
    failed = df[~df["valid_bo_result"].fillna(False)].copy()
    norm = Normalize(vmin=float(valid["yield_percent"].min()), vmax=float(valid["yield_percent"].max()))
    cmap = plt.get_cmap("viridis")

    fig, ax = plt.subplots(figsize=(9.5, 7.0), constrained_layout=True)
    # Scale marker area by catalyst loading.
    cat_min, cat_max = valid["catalyst_equiv"].min(), valid["catalyst_equiv"].max()
    def size(vals):
        denom = (cat_max - cat_min) if cat_max != cat_min else 1.0
        return 55 + 260 * (vals - cat_min) / denom

    for light, marker in MARKERS_BY_LIGHT.items():
        sub = valid[valid["light_intensity"].round().astype("Int64") == light]
        if sub.empty:
            continue
        ax.scatter(sub["residence_time_min"], sub["TFAA_equiv"], c=sub["yield_percent"], cmap=cmap, norm=norm, s=size(sub["catalyst_equiv"]), marker=marker, alpha=0.9, edgecolor="white", linewidth=0.6, label=f"{light}% light")
    if not failed.empty:
        ax.scatter(failed["residence_time_min"], failed["TFAA_equiv"], marker="x", c="#777777", s=85, linewidth=1.5, label="failed/unsubmitted")

    # Annotate valid experiment numbers; failed sample labels if compact.
    for _, row in valid.iterrows():
        ax.annotate(str(int(row["experiment"])), (row["residence_time_min"], row["TFAA_equiv"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    for _, row in failed.iterrows():
        label = str(row.get("sample_name") or "failed")
        ax.annotate(label.replace("bo_", ""), (row["residence_time_min"], row["TFAA_equiv"]), xytext=(4, -10), textcoords="offset points", fontsize=7, color="#666666")

    ax.set_xlabel("Residence time (min)")
    ax.set_ylabel("TFAA equiv")
    title = "Focused chemical map: residence time vs TFAA loading"
    if args.filter_main_region:
        title += "\nfiltered to Ru bpy Cl / py NO"
    else:
        title += "\nall catalyst/oxidant identities"
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    leg = ax.legend(title="Light intensity", fontsize=8, loc="best")
    cbar = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, pad=0.01)
    cbar.set_label("Yield (%)")
    ax.text(0.01, 0.01, "Marker area scales with catalyst_equiv", transform=ax.transAxes, fontsize=8, color="0.35", va="bottom")
    fig.text(0.01, 0.005, f"Source: {source}", fontsize=8, color="0.35")

    stem = "search_space_focused_residence_vs_TFAA_main_region" if args.filter_main_region else "search_space_focused_residence_vs_TFAA"
    png = args.outdir / f"{stem}.png"
    svg = args.outdir / f"{stem}.svg"
    fig.savefig(png, dpi=220)
    fig.savefig(svg)
    print(f"Read {len(df)} point rows from {source}")
    print(f"Wrote {png}\nWrote {svg}")

if __name__ == "__main__":
    main()
