#!/usr/bin/env python3
"""Generate helpful summary plots for the phosphine BO campaign.

All plotted campaign values are read from artifact files, primarily report.csv
and evaluation_records.jsonl. No campaign result values are embedded in code.

Outputs are written to <artifact-dir>/plots/ by default.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OBJECTIVES = ["donor_homo_error", "gap_error", "steric_excess", "heavy_atom_count"]
# Heavy-atom count is both a descriptor and an objective in the campaign record.
# Keep a single copy in descriptor/correlation views to avoid plotting it twice.
DESCRIPTORS = [
    "homo_energy_eV",
    "lumo_energy_eV",
    "homo_lumo_gap_eV",
    "phosphorus_partial_charge",
    "molecular_volume_ang3",
]
SUB_COLS = ["R1", "R2", "R3"]


def default_artifact_dir() -> Path:
    manifest = Path("campaign_manifest.json")
    if manifest.exists():
        data = json.loads(manifest.read_text())
        latest = data.get("latest_artifact_dir")
        if latest and Path(latest).exists():
            return Path(latest)
    candidates = sorted(Path("artifacts").glob("phosphine_electronics_*"))
    if not candidates:
        raise FileNotFoundError("No phosphine_electronics artifact directory found")
    return candidates[-1]


def load_report(artifact_dir: Path) -> pd.DataFrame:
    path = artifact_dir / "report.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df = df[df["status"].eq("success")].copy()
    for col in ["pareto", "representative_tradeoff"]:
        if col in df:
            df[col] = df[col].astype(bool)
    # Deduplicate heavy atom count if the flattened report contains both the
    # descriptor and objective copies. They are intentionally the same campaign
    # quantity, so keep one canonical column for all plots.
    if "heavy_atom_count.1" in df.columns:
        if "heavy_atom_count" not in df.columns:
            df = df.rename(columns={"heavy_atom_count.1": "heavy_atom_count"})
        else:
            df = df.drop(columns=["heavy_atom_count.1"])
    return df.reset_index(drop=True)


def load_eval_order(artifact_dir: Path) -> pd.DataFrame:
    path = artifact_dir / "evaluation_records.jsonl"
    rows = []
    with path.open() as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("status") != "success":
                continue
            rows.append({
                "eval_index": i,
                "candidate_id": rec.get("candidate_id"),
                "phase": rec.get("phase"),
                "timestamp": rec.get("timestamp"),
            })
    return pd.DataFrame(rows)


def ensure_outdir(artifact_dir: Path) -> Path:
    out = artifact_dir / "plots"
    out.mkdir(exist_ok=True)
    return out


def save(fig, outdir: Path, name: str) -> Path:
    path = outdir / name
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_electronic_map(df: pd.DataFrame, outdir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 7.2), dpi=180)
    phase_marker = {"warm_start": "o", "bo": "^"}
    last_sc = None
    for phase, marker in phase_marker.items():
        sub = df[df["phase"].eq(phase)]
        if sub.empty:
            continue
        sizes = 28 + 2.0 * sub["heavy_atom_count"].astype(float)
        last_sc = ax.scatter(
            sub["homo_energy_eV"],
            sub["homo_lumo_gap_eV"],
            s=sizes,
            c=sub["phosphorus_partial_charge"],
            cmap="viridis",
            marker=marker,
            alpha=0.76,
            edgecolor="white",
            linewidth=0.45,
            label=phase.replace("_", " "),
        )
    pareto = df[df["pareto"]]
    ax.scatter(
        pareto["homo_energy_eV"],
        pareto["homo_lumo_gap_eV"],
        s=95 + 2.2 * pareto["heavy_atom_count"].astype(float),
        facecolors="none",
        edgecolors="#d62728",
        linewidth=1.7,
        label="Pareto front",
    )
    reps = df[df.get("representative_tradeoff", False)].copy()
    for _, row in reps.iterrows():
        ax.annotate(
            f"{row['candidate_id']}\n{row['R1']}/{row['R2']}/{row['R3']}",
            (row["homo_energy_eV"], row["homo_lumo_gap_eV"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=7.2,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="0.75", alpha=0.78),
        )
    if last_sc is not None:
        cb = fig.colorbar(last_sc, ax=ax, pad=0.015)
        cb.set_label("Phosphorus partial charge / e")
    ax.set_xlabel("HOMO energy / eV")
    ax.set_ylabel("HOMO–LUMO gap / eV")
    ax.set_title("Electronic map of evaluated phosphines")
    ax.grid(True, alpha=0.23)
    ax.legend(loc="best", framealpha=0.95, fontsize=8)
    fig.tight_layout()
    return save(fig, outdir, "electronic_map_updated.png")


def plot_objective_scatter_matrix(df: pd.DataFrame, outdir: Path) -> Path:
    # Use objective columns; objective heavy atom count may share descriptor column in report.csv.
    cols = ["donor_homo_error", "gap_error", "steric_excess", "heavy_atom_count"]
    labels = {
        "donor_homo_error": "HOMO error / eV",
        "gap_error": "Gap error / eV",
        "steric_excess": "Steric excess / Å³",
        "heavy_atom_count": "Heavy atoms",
    }
    n = len(cols)
    fig, axes = plt.subplots(n, n, figsize=(11, 10.5), dpi=170)
    colors = np.where(df["pareto"], "#d62728", np.where(df["phase"].eq("bo"), "#1f77b4", "#7f7f7f"))
    markers = np.where(df["phase"].eq("bo"), "^", "o")
    for i, y in enumerate(cols):
        for j, x in enumerate(cols):
            ax = axes[i, j]
            if i == j:
                for pareto_flag, color, name in [(False, "#9e9e9e", "non-Pareto"), (True, "#d62728", "Pareto")]:
                    vals = df.loc[df["pareto"].eq(pareto_flag), x].dropna().astype(float)
                    if len(vals):
                        ax.hist(vals, bins=min(10, max(3, len(vals)//2)), alpha=0.55, color=color, label=name)
            else:
                for marker in ["o", "^"]:
                    mask = markers == marker
                    ax.scatter(df.loc[mask, x], df.loc[mask, y], c=colors[mask], marker=marker,
                               s=38, alpha=0.78, edgecolor="white", linewidth=0.35)
            if i == n - 1:
                ax.set_xlabel(labels[x], fontsize=8)
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(labels[y], fontsize=8)
            else:
                ax.set_yticklabels([])
            ax.grid(True, alpha=0.18)
    legend = [
        Line2D([0], [0], marker="o", color="w", label="warm start / non-Pareto", markerfacecolor="#7f7f7f", markersize=7),
        Line2D([0], [0], marker="^", color="w", label="BO / non-Pareto", markerfacecolor="#1f77b4", markersize=7),
        Line2D([0], [0], marker="o", color="w", label="Pareto", markerfacecolor="#d62728", markersize=7),
    ]
    fig.legend(handles=legend, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.01))
    fig.suptitle("Pairwise objective-space trade-offs", y=1.035, fontsize=13)
    fig.tight_layout()
    return save(fig, outdir, "objective_scatter_matrix.png")


def plot_parallel_coordinates(df: pd.DataFrame, outdir: Path) -> Path:
    cols = ["donor_homo_error", "gap_error", "steric_excess", "heavy_atom_count"]
    vals = df[cols].astype(float)
    mins, maxs = vals.min(), vals.max()
    norm = (vals - mins) / (maxs - mins).replace(0, 1.0)
    x = np.arange(len(cols))
    fig, ax = plt.subplots(figsize=(10.5, 6.2), dpi=180)
    for idx, row in norm.iterrows():
        is_p = bool(df.loc[idx, "pareto"])
        is_rep = bool(df.loc[idx, "representative_tradeoff"])
        if is_rep:
            color, alpha, lw, z = "#d62728", 0.95, 2.1, 3
        elif is_p:
            color, alpha, lw, z = "#ff9896", 0.8, 1.3, 2
        else:
            color, alpha, lw, z = "#bdbdbd", 0.28, 0.9, 1
        ax.plot(x, row.values, color=color, alpha=alpha, lw=lw, zorder=z)
    ax.set_xticks(x)
    ax.set_xticklabels(["HOMO\nerror", "gap\nerror", "steric\nexcess", "heavy\natoms"])
    ax.set_ylabel("Min-max normalized objective value\n(lower is better per axis)")
    ax.set_title("Normalized multi-objective profiles")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(handles=[
        Line2D([0], [0], color="#d62728", lw=2.1, label="representative trade-off"),
        Line2D([0], [0], color="#ff9896", lw=1.5, label="other Pareto"),
        Line2D([0], [0], color="#bdbdbd", lw=1.2, label="non-Pareto"),
    ], loc="upper right")
    fig.tight_layout()
    return save(fig, outdir, "parallel_objective_profiles.png")


def plot_substituent_enrichment(df: pd.DataFrame, outdir: Path) -> Path:
    all_counts = Counter(df[SUB_COLS].astype(str).values.ravel())
    pareto_counts = Counter(df.loc[df["pareto"], SUB_COLS].astype(str).values.ravel())
    subs = sorted(all_counts.keys())
    total_slots = sum(all_counts.values()) or 1
    pareto_slots = sum(pareto_counts.values()) or 1
    all_freq = np.array([all_counts[s] / total_slots for s in subs])
    pareto_freq = np.array([pareto_counts[s] / pareto_slots for s in subs])
    enrichment = np.divide(pareto_freq, all_freq, out=np.zeros_like(pareto_freq), where=all_freq > 0)

    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=180)
    x = np.arange(len(subs))
    ax.bar(x - 0.2, all_freq, width=0.4, color="#9e9e9e", label="all evaluated")
    ax.bar(x + 0.2, pareto_freq, width=0.4, color="#d62728", label="Pareto front")
    ax2 = ax.twinx()
    ax2.plot(x, enrichment, color="#1f77b4", marker="o", lw=1.8, label="Pareto enrichment ratio")
    ax.set_xticks(x)
    ax.set_xticklabels(subs, rotation=45, ha="right")
    ax.set_ylabel("Substituent slot frequency")
    ax2.set_ylabel("Pareto enrichment ratio")
    ax.set_title("Substituent representation in evaluated vs Pareto ligands")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", framealpha=0.95)
    ax.grid(True, axis="y", alpha=0.22)
    fig.tight_layout()
    return save(fig, outdir, "substituent_pareto_enrichment.png")


def plot_descriptor_correlation(df: pd.DataFrame, outdir: Path) -> Path:
    cols = []
    for c in DESCRIPTORS + OBJECTIVES:
        if c in df.columns and c not in cols:
            cols.append(c)
    corr = df[cols].astype(float).corr()
    fig, ax = plt.subplots(figsize=(10, 8.5), dpi=180)
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(np.arange(len(cols)))
    ax.set_yticks(np.arange(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=7.5)
    ax.set_yticklabels(cols, fontsize=7.5)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{corr.iloc[i,j]:.2f}", ha="center", va="center", fontsize=6.5,
                    color="white" if abs(corr.iloc[i,j]) > 0.55 else "black")
    cb = fig.colorbar(im, ax=ax, shrink=0.82)
    cb.set_label("Pearson correlation")
    ax.set_title("Descriptor/objective correlation across evaluated ligands")
    fig.tight_layout()
    return save(fig, outdir, "descriptor_objective_correlation.png")


def plot_phase_objective_distributions(df: pd.DataFrame, outdir: Path) -> Path:
    cols = ["donor_homo_error", "gap_error", "heavy_atom_count", "molecular_volume_ang3"]
    labels = ["HOMO error / eV", "Gap error / eV", "Heavy atoms", "Volume proxy / Å³"]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.5), dpi=180)
    axes = axes.ravel()
    phases = [p for p in ["warm_start", "bo"] if p in set(df["phase"])]
    colors = {"warm_start": "#7f7f7f", "bo": "#1f77b4"}
    for ax, col, lab in zip(axes, cols, labels):
        data = [df.loc[df["phase"].eq(p), col].dropna().astype(float).values for p in phases]
        bp = ax.boxplot(data, tick_labels=[p.replace("_", " ") for p in phases], patch_artist=True, showfliers=False)
        for patch, p in zip(bp["boxes"], phases):
            patch.set_facecolor(colors[p]); patch.set_alpha(0.45)
        for i, p in enumerate(phases, start=1):
            vals = df.loc[df["phase"].eq(p), col].dropna().astype(float).values
            jitter = np.linspace(-0.06, 0.06, len(vals)) if len(vals) else []
            ax.scatter(np.full(len(vals), i) + jitter, vals, s=24, color=colors[p], alpha=0.7,
                       edgecolor="white", linewidth=0.3)
        ax.set_ylabel(lab)
        ax.grid(True, axis="y", alpha=0.22)
    fig.suptitle("Warm-start vs BO-guided evaluation distributions", y=1.02, fontsize=13)
    fig.tight_layout()
    return save(fig, outdir, "phase_objective_distributions.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-dir", type=Path, default=None)
    args = ap.parse_args()
    artifact_dir = args.artifact_dir or default_artifact_dir()
    outdir = ensure_outdir(artifact_dir)
    df = load_report(artifact_dir)
    order = load_eval_order(artifact_dir)
    if not order.empty:
        df = df.merge(order[["candidate_id", "eval_index"]], on="candidate_id", how="left")
        df = df.sort_values("eval_index", na_position="last").reset_index(drop=True)
    paths = [
        plot_electronic_map(df, outdir),
        plot_objective_scatter_matrix(df, outdir),
        plot_parallel_coordinates(df, outdir),
        plot_substituent_enrichment(df, outdir),
        plot_descriptor_correlation(df, outdir),
        plot_phase_objective_distributions(df, outdir),
    ]
    manifest = outdir / "plot_manifest.txt"
    manifest.write_text("\n".join(str(p) for p in paths) + "\n")
    print(f"Wrote {len(paths)} plots to {outdir}")
    for p in paths:
        print(p)
    print(manifest)


if __name__ == "__main__":
    main()
