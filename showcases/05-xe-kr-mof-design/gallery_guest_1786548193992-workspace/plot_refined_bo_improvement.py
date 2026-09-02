#!/usr/bin/env python3
"""Plot the refined Xe/Kr MOF BO improvement curve from campaign_export.csv.

This handles the refined campaign's finite `param_candidate_id` representation
(`topology|node|edge`) and its historical seed rows. The score matches the
campaign desirability scalarization:

    score = selectivity_proxy^0.6 * (capacity_proxy / 10)^0.4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def score_frame(df: pd.DataFrame, seed_count: int, capacity_upper: float = 10.0) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "eval_in_export", range(1, len(out) + 1))
    out["phase"] = ["seed" if i <= seed_count else "new" for i in out["eval_in_export"]]
    out["new_eval"] = [0 if i <= seed_count else i - seed_count for i in out["eval_in_export"]]

    sel = pd.to_numeric(out["obj_selectivity_proxy"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    cap_raw = pd.to_numeric(out["obj_capacity_proxy"], errors="coerce").fillna(0.0)
    cap = (cap_raw / capacity_upper).clip(0.0, 1.0)
    out["candidate"] = out.get("param_candidate_id", pd.Series([""] * len(out))).astype(str).str.replace("|", "_", regex=False)
    out["selectivity_proxy"] = sel
    out["capacity_proxy_cm3_g"] = cap_raw
    out["scalarized_desirability"] = (sel.pow(0.6) * cap.pow(0.4)).where((sel > 0) & (cap > 0), 0.0)
    out["best_so_far"] = out["scalarized_desirability"].cummax()
    return out


def incumbent_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    best = -1.0
    for _, row in df.iterrows():
        s = float(row["scalarized_desirability"])
        if s > best + 1e-12:
            rows.append(row)
            best = s
    return pd.DataFrame(rows)


def plot(df: pd.DataFrame, output_png: Path, output_pdf: Path, seed_count: int) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=180)

    seed_df = df[df["phase"] == "seed"]
    new_df = df[df["phase"] == "new"]

    ax.plot(df["eval_in_export"], df["scalarized_desirability"], color="0.55", lw=1.0, alpha=0.65)
    ax.scatter(seed_df["eval_in_export"], seed_df["scalarized_desirability"], s=25, color="#4c78a8", label="Historical seed observations")
    ax.scatter(new_df["eval_in_export"], new_df["scalarized_desirability"], s=25, color="#59a14f", label="Refined follow-up observations")
    ax.step(df["eval_in_export"], df["best_so_far"], where="post", color="#d62728", lw=2.7, label="Best-so-far")

    if seed_count > 0:
        ax.axvspan(0.5, seed_count + 0.5, color="#4c78a8", alpha=0.08)
        ax.axvline(seed_count + 0.5, color="black", lw=1.0, ls="--", alpha=0.65)
        ax.text(seed_count + 0.7, 0.02, "50-eval refined follow-up starts", rotation=90, va="bottom", fontsize=8)

    for _, row in incumbent_rows(df).iterrows():
        if float(row["scalarized_desirability"]) <= 0.0:
            continue
        ax.annotate(
            f"{row['candidate']}\n{row['scalarized_desirability']:.3f}",
            xy=(row["eval_in_export"], row["best_so_far"]),
            xytext=(6, 8),
            textcoords="offset points",
            fontsize=7.2,
            arrowprops=dict(arrowstyle="-", lw=0.5, color="0.35"),
            bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="0.8", alpha=0.88),
        )

    best = df.loc[df["scalarized_desirability"].idxmax()]
    summary = (
        f"Best: {best['candidate']}\n"
        f"score={best['scalarized_desirability']:.3f}, "
        f"sel={best['selectivity_proxy']:.3f}, "
        f"cap={best['capacity_proxy_cm3_g']:.3f} cm³/g"
    )
    ax.text(0.02, 0.96, summary, transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.65", alpha=0.95))

    ax.set_title("Updated BO Improvement Curve: Refined Xe/Kr PORMAKE MOF Campaign")
    ax.set_xlabel("Observation in follow-up export (15 historical seeds + 50 new evaluations)")
    ax.set_ylabel("Weighted geometric desirability\n(selectivity^0.6 × (capacity/10)^0.4)")
    ax.set_xlim(0.5, len(df) + 0.5)
    ax.set_ylim(-0.01, max(0.58, float(df["best_so_far"].max()) * 1.12))
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(output_png, bbox_inches="tight")
    fig.savefig(output_pdf, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-csv", default="xe_kr_mof_bo_refined_artifacts/20260812_163546/campaign_export.csv")
    parser.add_argument("--seed-count", type=int, default=15)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    export_csv = Path(args.export_csv)
    outdir = Path(args.output_dir) if args.output_dir else export_csv.parent
    outdir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(export_csv)
    scored = score_frame(raw, seed_count=args.seed_count)
    scored_csv = outdir / "updated_bo_improvement_curve.csv"
    png = outdir / "updated_bo_improvement_curve.png"
    pdf = outdir / "updated_bo_improvement_curve.pdf"
    scored.to_csv(scored_csv, index=False)
    plot(scored, png, pdf, seed_count=args.seed_count)

    best = scored.loc[scored["scalarized_desirability"].idxmax()]
    print(f"Wrote: {png}")
    print(f"Wrote: {pdf}")
    print(f"Wrote: {scored_csv}")
    print(
        f"Best: observation={int(best['eval_in_export'])} new_eval={int(best['new_eval'])} "
        f"candidate={best['candidate']} score={best['scalarized_desirability']:.6f} "
        f"selectivity={best['selectivity_proxy']:.6f} capacity_cm3_g={best['capacity_proxy_cm3_g']:.6f}"
    )
    print("Incumbent improvements:")
    for _, r in incumbent_rows(scored).iterrows():
        print(
            f"  obs={int(r['eval_in_export']):02d} new_eval={int(r['new_eval']):02d} "
            f"{r['candidate']} score={r['scalarized_desirability']:.6f} "
            f"sel={r['selectivity_proxy']:.4f} cap={r['capacity_proxy_cm3_g']:.4f}"
        )


if __name__ == "__main__":
    main()
