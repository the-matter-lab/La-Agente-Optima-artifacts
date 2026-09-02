#!/usr/bin/env python3
"""Regenerate BO improvement plots from data/evaluation_results.csv.

Run from the reproduction folder:
    python scripts/plot_bo_improvement.py
"""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "evaluation_results.csv"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

df = pd.read_csv(RESULTS)
df["attempt_index"] = range(1, len(df) + 1)
for c in ["objective", "delta_est_ev", "S1_ev", "T1_ev", "oscillator_strength", "total_eval_wall_s"]:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

succ = df[df["status"].eq("success")].copy()
succ["success_index"] = range(1, len(succ) + 1)
succ["best_objective_so_far"] = succ["objective"].cummax()
succ["best_delta_so_far"] = succ["delta_est_ev"].cummin()
succ["is_new_best"] = succ["objective"].eq(succ["best_objective_so_far"]) & ~succ["best_objective_so_far"].duplicated()
newbest = succ[succ["is_new_best"]]
best = succ.loc[succ["objective"].idxmax()]

fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, constrained_layout=True)

ax = axes[0]
ax.plot(succ["success_index"], succ["objective"], marker="o", linestyle="-", alpha=0.45, label="observed objective")
ax.step(succ["success_index"], succ["best_objective_so_far"], where="post", linewidth=2.5, label="best objective so far")
ax.scatter(newbest["success_index"], newbest["objective"], s=80, zorder=3, label="new best")
for _, r in newbest.iterrows():
    ax.annotate(str(int(r["success_index"])), (r["success_index"], r["objective"]), textcoords="offset points", xytext=(4, 5), fontsize=8)
ax.set_ylabel("Objective = -(S1 - T1) / eV")
ax.set_title("BO improvement curve: Pollice 2021 lowest-conformer TD-DFT gap")
ax.grid(True, alpha=0.3)
ax.legend(loc="best")

ax = axes[1]
ax.plot(succ["success_index"], succ["delta_est_ev"], marker="o", linestyle="-", alpha=0.45, label="observed gap")
ax.step(succ["success_index"], succ["best_delta_so_far"], where="post", linewidth=2.5, label="smallest gap so far")
ax.scatter(newbest["success_index"], newbest["delta_est_ev"], s=80, zorder=3, label="new smallest gap")
for _, r in newbest.iterrows():
    ax.annotate(str(int(r["success_index"])), (r["success_index"], r["delta_est_ev"]), textcoords="offset points", xytext=(4, 5), fontsize=8)
ax.set_xlabel("Successful evaluation number")
ax.set_ylabel("delta_est_ev = S1 - T1 / eV")
ax.grid(True, alpha=0.3)
ax.legend(loc="best")

n_success = len(succ)
n_failed = int((df["status"] != "success").sum())
fig.text(0.01, 0.003, f"n_success={n_success}, n_failed={n_failed}; best={best['molecule_key']} delta={best['delta_est_ev']:.6f} eV objective={best['objective']:.6f}", fontsize=9)

png = PLOTS / "bo_improvement_curve.png"
pdf = PLOTS / "bo_improvement_curve.pdf"
csv = PLOTS / "bo_improvement_curve_data.csv"
fig.savefig(png, dpi=300)
fig.savefig(pdf)
succ[["attempt_index", "success_index", "molecule_key", "objective", "delta_est_ev", "best_objective_so_far", "best_delta_so_far", "is_new_best", "status"]].to_csv(csv, index=False)
print(f"Wrote {png}")
print(f"Wrote {pdf}")
print(f"Wrote {csv}")
