#!/usr/bin/env python3
"""Plot a BO improvement curve from a BO-MCP campaign export CSV.

The Xe/Kr MOF campaign used BayBE desirability scalarization with objectives:
  - selectivity_proxy, normalized on [0, 1], weight 0.6
  - capacity_proxy, normalized on [0, 10] cm^3/g, weight 0.4

This script reads the exported BO-MCP CSV in evaluation order, computes the same
weighted geometric desirability score, and plots observed scores plus the
best-so-far improvement curve.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def clipped01(x: pd.Series) -> pd.Series:
    return x.clip(lower=0.0, upper=1.0)


def compute_scores(
    df: pd.DataFrame,
    selectivity_col: str = "obj_selectivity_proxy",
    capacity_col: str = "obj_capacity_proxy",
    capacity_upper: float = 10.0,
    selectivity_weight: float = 0.6,
    capacity_weight: float = 0.4,
) -> pd.DataFrame:
    """Return dataframe with scalarized desirability and best-so-far columns."""
    missing = [c for c in [selectivity_col, capacity_col] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s) in export CSV: {missing}")

    out = df.copy()
    out.insert(0, "eval", range(1, len(out) + 1))

    sel = clipped01(pd.to_numeric(out[selectivity_col], errors="coerce").fillna(0.0))
    cap = clipped01(pd.to_numeric(out[capacity_col], errors="coerce").fillna(0.0) / capacity_upper)

    # Geometric desirability is zero if either objective desirability is zero.
    score = (sel.pow(selectivity_weight) * cap.pow(capacity_weight)).where(
        (sel > 0.0) & (cap > 0.0),
        0.0,
    )
    out["scalarized_desirability"] = score
    out["best_so_far"] = out["scalarized_desirability"].cummax()

    topo = out.get("param_topology", pd.Series([""] * len(out), index=out.index)).astype(str)
    node = out.get("param_node", pd.Series([""] * len(out), index=out.index)).astype(str)
    edge = out.get("param_edge", pd.Series([""] * len(out), index=out.index)).astype(str)
    out["candidate"] = topo + "_" + node + "_" + edge
    out["selectivity_proxy"] = sel
    out["capacity_proxy_cm3_g"] = pd.to_numeric(out[capacity_col], errors="coerce").fillna(0.0)
    return out


def incumbent_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    best = -1.0
    for _, row in df.iterrows():
        value = float(row["scalarized_desirability"])
        if value > best + 1e-12:
            rows.append(row)
            best = value
    return pd.DataFrame(rows)


def plot_curve(df: pd.DataFrame, output_png: Path, output_pdf: Path | None = None) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6), dpi=180)

    ax.plot(
        df["eval"],
        df["scalarized_desirability"],
        marker="o",
        ms=4,
        lw=1.0,
        alpha=0.55,
        label="Observed scalarized score",
    )
    ax.step(
        df["eval"],
        df["best_so_far"],
        where="post",
        lw=2.6,
        color="#d62728",
        label="Best-so-far improvement",
    )

    # Campaign settings: initial design size 9 and batch size 3.
    ax.axvspan(0.5, 9.5, color="#4c78a8", alpha=0.08, label="Initial design (9 evals)")
    for x in range(9, len(df) + 1, 3):
        ax.axvline(x + 0.5, color="0.75", lw=0.6, ls="--", alpha=0.7)

    for _, row in incumbent_rows(df).iterrows():
        if float(row["scalarized_desirability"]) <= 0.0:
            continue
        ax.annotate(
            str(row["candidate"]),
            xy=(row["eval"], row["best_so_far"]),
            xytext=(6, 8),
            textcoords="offset points",
            fontsize=7.5,
            arrowprops=dict(arrowstyle="-", lw=0.5, color="0.35"),
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.8", alpha=0.85),
        )

    best = df.loc[df["scalarized_desirability"].idxmax()]
    summary = (
        f"Best: {best['candidate']}\n"
        f"score={best['scalarized_desirability']:.3f}, "
        f"sel={best['selectivity_proxy']:.3f}, "
        f"cap={best['capacity_proxy_cm3_g']:.3f} cm³/g"
    )
    ax.text(
        0.02,
        0.96,
        summary,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.65", alpha=0.95),
    )

    ax.set_title("BO Improvement Curve: Xe/Kr PORMAKE MOF Campaign")
    ax.set_xlabel("Evaluation number")
    ax.set_ylabel("Weighted geometric desirability\n(selectivity^0.6 × (capacity/10)^0.4)")
    ax.set_xlim(0.5, len(df) + 0.5)
    ax.set_ylim(bottom=-0.01, top=max(0.55, float(df["best_so_far"].max()) * 1.12))
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()

    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, bbox_inches="tight")
    if output_pdf is not None:
        fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-csv",
        default="xe_kr_mof_bo_artifacts/20260812_154010/campaign_export.csv",
        help="Path to BO-MCP campaign_export.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for plot outputs. Defaults to the export CSV directory.",
    )
    parser.add_argument("--capacity-upper", type=float, default=10.0)
    parser.add_argument("--selectivity-weight", type=float, default=0.6)
    parser.add_argument("--capacity-weight", type=float, default=0.4)
    args = parser.parse_args()

    export_csv = Path(args.export_csv)
    output_dir = Path(args.output_dir) if args.output_dir else export_csv.parent

    raw = pd.read_csv(export_csv)
    scored = compute_scores(
        raw,
        capacity_upper=args.capacity_upper,
        selectivity_weight=args.selectivity_weight,
        capacity_weight=args.capacity_weight,
    )

    scored_csv = output_dir / "bo_improvement_curve_from_export.csv"
    output_png = output_dir / "bo_improvement_curve_from_export.png"
    output_pdf = output_dir / "bo_improvement_curve_from_export.pdf"

    scored.to_csv(scored_csv, index=False)
    plot_curve(scored, output_png, output_pdf)

    best = scored.loc[scored["scalarized_desirability"].idxmax()]
    print(f"Wrote: {output_png}")
    print(f"Wrote: {output_pdf}")
    print(f"Wrote: {scored_csv}")
    print(
        "Best: "
        f"eval={int(best['eval'])} candidate={best['candidate']} "
        f"score={best['scalarized_desirability']:.6f} "
        f"selectivity={best['selectivity_proxy']:.6f} "
        f"capacity_cm3_g={best['capacity_proxy_cm3_g']:.6f}"
    )


if __name__ == "__main__":
    main()
