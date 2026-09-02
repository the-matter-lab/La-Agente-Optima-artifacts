#!/usr/bin/env python3
"""Plot yield/green-score Pareto front for the RoboChemFlex BO campaign.

Reads a BO-MCP export CSV (or auto-discovers the most complete/latest export),
computes non-dominated points for simultaneous maximization of yield_percent
and green_score, and highlights the Pareto-optimal observations.
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
        "xtick.labelsize": 5,
        "ytick.labelsize": 5,
        "axes.linewidth": 0.4,
        "axes.labelpad": 1.5,
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
DEFAULT_SEARCH_ROOT = Path("artifacts/recreated_robochemflex_yield_bo_20260725")
DEFAULT_OUTDIR = Path("plots")


def green_score(candidate: dict) -> float:
    """Compute the campaign's documented condition-efficiency audit metric."""
    catalyst = (float(candidate["catalyst_equiv"]) - 0.001) / (0.004 - 0.001)
    tfaa = (float(candidate["TFAA_equiv"]) - 0.9) / (3.5 - 0.9)
    oxidant = (float(candidate["oxidant_equiv"]) - 0.9) / (3.0 - 0.9)
    photonic = (float(candidate["light_intensity"]) / 100.0) * (
        (float(candidate["residence_time_min"]) - 2.0) / (90.0 - 2.0)
    )
    penalty = 0.25 * (catalyst + tfaa + oxidant + photonic)
    return max(0.0, min(100.0, 100.0 * (1.0 - penalty)))


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


def load_export(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    required = {
        "obj_yield_percent",
        "param_catalyst_equiv",
        "param_TFAA_equiv",
        "param_oxidant_equiv",
        "param_light_intensity",
        "param_residence_time_min",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required column(s): {sorted(missing)}")
    df["experiment"] = np.arange(1, len(df) + 1)
    df["yield_percent"] = pd.to_numeric(df["obj_yield_percent"], errors="raise")
    if "obj_green_score" in df:
        df["green_score"] = pd.to_numeric(df["obj_green_score"], errors="raise")
        df["green_score_source"] = "campaign objective"
    else:
        df["green_score"] = df.apply(
            lambda row: green_score(
                {
                    "catalyst_equiv": row["param_catalyst_equiv"],
                    "TFAA_equiv": row["param_TFAA_equiv"],
                    "oxidant_equiv": row["param_oxidant_equiv"],
                    "light_intensity": row["param_light_intensity"],
                    "residence_time_min": row["param_residence_time_min"],
                }
            ),
            axis=1,
        )
        df["green_score_source"] = "computed audit metric"
    # Avoid treating numerically identical boundary scores as distinct objectives.
    df["green_score"] = df["green_score"].round(12)
    return df


def pareto_mask_maximize(df: pd.DataFrame, x: str = "green_score", y: str = "yield_percent") -> np.ndarray:
    values = df[[x, y]].to_numpy(dtype=float)
    n = len(values)
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        # j dominates i if j is >= in both objectives and > in at least one.
        dominated_by_any = np.any(np.all(values >= values[i], axis=1) & np.any(values > values[i], axis=1))
        mask[i] = not dominated_by_any
    return mask


def plot(df: pd.DataFrame, outdir: Path, seed_count: int, yield_only_start: int) -> tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["stage"] = np.select(
        [df["experiment"] <= seed_count, df["experiment"] < yield_only_start],
        ["seed", "mixed-objective BO"],
        default="yield-only BO",
    )
    df["pareto_optimal"] = pareto_mask_maximize(df)
    pareto = df[df["pareto_optimal"]].copy().sort_values(["green_score", "yield_percent"])

    fig, ax = plt.subplots(figsize=(8 * CM, 6 * CM), dpi=600)
    colors = {"seed": "#4C78A8", "mixed-objective BO": "#F58518", "yield-only BO": "#54A24B"}
    markers = {"seed": "o", "mixed-objective BO": "o", "yield-only BO": "D"}
    pareto_color = "#303030"

    for stage, sub in df.groupby("stage", sort=False):
        ax.scatter(
            sub["green_score"], sub["yield_percent"], s=10, color=colors[stage],
            marker=markers[stage], edgecolor="white", linewidth=0.35, label=stage, zorder=3,
        )

    # Preserve the stage-colored markers and identify Pareto points with a
    # restrained charcoal halo rather than a competing highlight color.
    ax.scatter(
        pareto["green_score"], pareto["yield_percent"], s=20,
        facecolor="none", edgecolor=pareto_color, linewidth=0.55, zorder=4,
    )
    if len(pareto) > 1:
        ax.step(
            pareto["green_score"], pareto["yield_percent"], where="post",
            color=pareto_color, linewidth=0.65, linestyle="--", alpha=0.75,
            label="Pareto front", zorder=2,
        )

    # Annotate Pareto points with experiment numbers.
    for _, row in pareto.iterrows():
        experiment = int(row["experiment"])
        if experiment == 12:
            offset, ha, va = (-3, 3), "right", "bottom"
        elif experiment == 14:
            offset, ha, va = (3, -3), "left", "top"
        else:
            offset, ha, va = (3, 3), "left", "bottom"
        ax.annotate(
            str(experiment), (row["green_score"], row["yield_percent"]),
            xytext=offset, textcoords="offset points", fontsize=5,
            color=pareto_color, ha=ha, va=va,
        )

    # Annotate all points lightly with experiment numbers for traceability.
    for _, row in df.iterrows():
        if not row["pareto_optimal"]:
            ax.annotate(str(int(row["experiment"])), (row["green_score"], row["yield_percent"]), xytext=(2, -5), textcoords="offset points", fontsize=4, color="0.35", alpha=0.75)

    ax.set_xlabel("green score")
    ax.set_ylabel("yield (%)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower left", ncol=2, frameon=False, handlelength=1.5, columnspacing=0.8)
    ax.set_xlim(max(0, df["green_score"].min() - 5), min(105, df["green_score"].max() + 5))
    ax.set_ylim(max(0, df["yield_percent"].min() - 5), min(105, df["yield_percent"].max() + 8))
    plt.tight_layout(pad=0.3)

    png = outdir / "pareto_front_yield_green.png"
    svg = outdir / "pareto_front_yield_green.svg"
    csv_out = outdir / "pareto_front_points.csv"
    fig.savefig(png, transparent=True)
    fig.savefig(svg, transparent=True)
    plt.close(fig)
    df.to_csv(outdir / "pareto_front_all_points.csv", index=False)
    pareto.to_csv(csv_out, index=False)
    return png, svg, csv_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None, help="BO-MCP export CSV. Auto-discovered if omitted.")
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--seed-count", type=int, default=6)
    parser.add_argument("--yield-only-start", type=int, default=21)
    parser.add_argument("--exclude-experiments", type=str, default="", help="Comma-separated successful-measurement numbers to omit")
    args = parser.parse_args()

    source = args.input or discover_export(args.search_root)
    df = load_export(source)
    excluded = []
    if args.exclude_experiments.strip():
        excluded = [int(x.strip()) for x in args.exclude_experiments.split(",") if x.strip()]
        df = df[~df["experiment"].isin(excluded)].copy()
    png, svg, csv_out = plot(df, args.outdir, args.seed_count, args.yield_only_start)
    print(f"Read {len(df)} experiments from {source}")
    if excluded:
        print(f"Excluded measurement numbers: {excluded}")
    print(f"Green score source: {df['green_score_source'].iloc[0]}")
    print(f"Wrote {png}")
    print(f"Wrote {svg}")
    print(f"Wrote {csv_out}")


if __name__ == "__main__":
    main()
