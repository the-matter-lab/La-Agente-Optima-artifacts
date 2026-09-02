#!/usr/bin/env python3
"""Plot compact per-parameter coverage for successful BO measurements."""
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
        "xtick.labelsize": 5,
        "ytick.labelsize": 5,
        "axes.linewidth": 0.4,
        "axes.labelpad": 2,
        "xtick.major.width": 0.4,
        "xtick.major.size": 1.5,
        "xtick.major.pad": 1.5,
        "legend.fontsize": 5,
    }
)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CM = 1 / 2.54

PARAMETERS = [
    {
        "column": "param_catalyst_type",
        "label": "catalyst type",
        "kind": "categorical",
        "values": ["Ru bpy Cl", "Ru bpy PF6", "Ir ppy", "Ir CF3 ppy", "4CzIPN"],
    },
    {
        "column": "param_oxidant_type",
        "label": "oxidant type",
        "kind": "categorical",
        "values": ["py NO", "4-Ph py NO"],
    },
    {
        "column": "param_catalyst_equiv",
        "label": "catalyst equiv.",
        "kind": "continuous",
        "bounds": (0.001, 0.004),
        "ticks": [0.001, 0.0025, 0.004],
    },
    {
        "column": "param_TFAA_equiv",
        "label": "TFAA equiv.",
        "kind": "continuous",
        "bounds": (0.9, 3.5),
        "ticks": [0.9, 2.2, 3.5],
    },
    {
        "column": "param_oxidant_equiv",
        "label": "oxidant equiv.",
        "kind": "continuous",
        "bounds": (0.9, 3.0),
        "ticks": [0.9, 1.95, 3.0],
    },
    {
        "column": "param_light_intensity",
        "label": "light intensity (%)",
        "kind": "discrete",
        "bounds": (0, 100),
        "ticks": [0, 25, 50, 75, 100],
    },
    {
        "column": "param_residence_time_min",
        "label": "residence time (min)",
        "kind": "continuous",
        "bounds": (2, 90),
        "ticks": [2, 46, 90],
    },
]

COLORS = {
    "seed": "#4C78A8",
    "mixed-objective BO": "#F58518",
    "yield-only BO": "#54A24B",
}
MARKERS = {"seed": "o", "mixed-objective BO": "o", "yield-only BO": "D"}


def load(path: Path, seed_count: int, yield_only_start: int) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    missing = {spec["column"] for spec in PARAMETERS} - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required column(s): {sorted(missing)}")
    df["experiment"] = np.arange(1, len(df) + 1)
    df["stage"] = np.select(
        [df["experiment"] <= seed_count, df["experiment"] < yield_only_start],
        ["seed", "mixed-objective BO"],
        default="yield-only BO",
    )
    return df


def categorical_positions(series: pd.Series, values: list[str]) -> np.ndarray:
    mapping = {value: i for i, value in enumerate(values)}
    unknown = sorted(set(series.astype(str)) - set(mapping))
    if unknown:
        raise ValueError(f"Unknown categorical value(s): {unknown}")
    return series.astype(str).map(mapping).to_numpy(dtype=float)


def compact_number(value: float) -> str:
    return f"{value:g}"


def packed_lanes(values: np.ndarray) -> np.ndarray:
    """Vertically pack repeated values while leaving unique values centered."""
    lanes = np.zeros(len(values), dtype=float)
    for value in np.unique(values):
        indices = np.flatnonzero(np.isclose(values, value, rtol=0, atol=1e-12))
        if len(indices) > 1:
            lanes[indices] = np.linspace(-0.2, 0.2, len(indices))
    return lanes


def plot(df: pd.DataFrame, outdir: Path) -> tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(PARAMETERS), 1, figsize=(8.5 * CM, 8.5 * CM), dpi=600)

    for ax, spec in zip(axes, PARAMETERS):
        if spec["kind"] == "categorical":
            values = spec["values"]
            x = categorical_positions(df[spec["column"]], values)
            ax.set_xlim(-0.35, len(values) - 0.65)
            ax.set_xticks(range(len(values)), values)
        else:
            lo, hi = spec["bounds"]
            x = pd.to_numeric(df[spec["column"]], errors="raise").to_numpy(dtype=float)
            pad = 0.025 * (hi - lo)
            ax.set_xlim(lo - pad, hi + pad)
            ax.set_xticks(spec["ticks"], [compact_number(v) for v in spec["ticks"]])

        lanes = packed_lanes(x)
        ax.axhline(0, color="0.72", linewidth=0.5, zorder=0)
        for stage in COLORS:
            mask = df["stage"].eq(stage).to_numpy()
            ax.scatter(
                x[mask], lanes[mask], s=10, marker=MARKERS[stage],
                color=COLORS[stage], edgecolor="white", linewidth=0.35,
                label=stage, zorder=3,
            )

        ax.set_ylabel(spec["label"], rotation=0, ha="right", va="center")
        ax.set_ylim(-0.26, 0.26)
        ax.set_yticks([])
        ax.grid(axis="x", color="0.85", linewidth=0.4, alpha=0.7)
        for side in ("left", "right", "top"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("0.55")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", ncol=3, frameon=False,
        bbox_to_anchor=(0.5, 0.995), handletextpad=0.4, columnspacing=0.9,
    )
    fig.subplots_adjust(left=0.31, right=0.985, top=0.92, bottom=0.055, hspace=0.9)

    png = outdir / "search_space_coverage_compact.png"
    svg = outdir / "search_space_coverage_compact.svg"
    csv_out = outdir / "search_space_coverage_compact_data.csv"
    fig.savefig(png, transparent=True)
    fig.savefig(svg, transparent=True)
    plt.close(fig)
    df.to_csv(csv_out, index=False)
    return png, svg, csv_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, default=Path("plots/search_space_coverage"))
    parser.add_argument("--seed-count", type=int, default=6)
    parser.add_argument("--yield-only-start", type=int, default=21)
    parser.add_argument("--exclude-experiments", type=str, default="")
    args = parser.parse_args()

    df = load(args.input, args.seed_count, args.yield_only_start)
    excluded = []
    if args.exclude_experiments.strip():
        excluded = [int(x.strip()) for x in args.exclude_experiments.split(",") if x.strip()]
        df = df[~df["experiment"].isin(excluded)].copy()

    png, svg, csv_out = plot(df, args.outdir)
    print(f"Read {len(df)} successful/submitted measurements from {args.input}")
    if excluded:
        print(f"Excluded measurement numbers: {excluded}")
    print(f"Wrote {png}\nWrote {svg}\nWrote {csv_out}")


if __name__ == "__main__":
    main()
