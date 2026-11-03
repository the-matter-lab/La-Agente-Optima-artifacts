"""Metrics and figures for the 2026-10-06b dihedral architecture comparison (commit 0949c2d1).

Reads data/runs.json (extract_data.py), data/logfire_totals.json, the 9/23 metrics and the
August summary; writes data/summary.json and figures/*.png. Run with the orchestrator
environment (numpy, matplotlib).
"""

import itertools
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
K = 627.509474  # kcal/mol per hartree
RATE_UNCACHED, RATE_CACHED, RATE_OUTPUT = 2.50e-6, 0.25e-6, 15.0e-6  # USD per token, from Logfire costs

ARMS = ["Standard", "Main-script", "Tool-loop", "Local-BO"]
COLOR = {"Standard": "#2a78d6", "Main-script": "#eb6834", "Tool-loop": "#1baf7a", "Local-BO": "#eda100"}
MARKER = {"Standard": "o", "Main-script": "s", "Tool-loop": "^", "Local-BO": "D"}
LINESTYLE = {1: "-", 2: (0, (5, 2)), 3: (0, (1.2, 1.6))}
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
REFERENCE_RUN = ("Standard", 1)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "xtick.color": INK2,
        "ytick.color": INK2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "figure.dpi": 100,
        "savefig.dpi": 300,
        "savefig.facecolor": "white",
    }
)


def angdiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def save(fig, name):
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)


runs = json.loads((DATA / "runs.json").read_text())
logfire = json.loads((DATA / "logfire_totals.json").read_text())["by_trace"]
runs.sort(key=lambda r: (ARMS.index(r["arm"]), r["repeat"]))
key = lambda r: (r["arm"], r["repeat"])
label = lambda r: f"{r['arm']} r{r['repeat']}"

# ---------- per-run metrics ----------
for r in runs:
    e = np.asarray(r["energies"], dtype=float)
    bsf = np.minimum.accumulate(e)
    assert np.allclose(bsf, r["best_so_far"]), label(r)
    r["bsf"] = bsf.tolist()
    first, best = e[0], bsf[-1]
    q = (first - bsf) / (first - best) if first > best else np.ones_like(bsf)
    r["q"] = q.tolist()
    for h in (10, 30, 60):
        r[f"auc{h}"] = float(np.trapezoid(q[:h], dx=1) / (h - 1))
    r["mbsf60"] = float(np.mean(q))
    r["evals_to_90pct"] = int(np.argmax(q >= 0.9) + 1)
    r["evals_to_best"] = int(np.argmin(e) + 1)
    r["improvement_kcal"] = float((first - best) * K)
    gaps = (e - best) * K
    r["frac_within_1kcal_of_own_best"] = float(np.mean(gaps <= 1.0))
    r["median_gap_to_own_best_kcal"] = float(np.median(gaps))
    cells = {tuple(int(((p[k] + 180.0) % 360.0) // 30) for k in ("cccc", "ccco", "ccoh")) for p in r["params"]}
    r["distinct_30deg_cells"] = len(cells)
    nn = []
    for i, p in enumerate(r["params"]):
        d = [max(angdiff(p[k], q2[k]) for k in p) for j, q2 in enumerate(r["params"]) if j != i]
        nn.append(min(d))
    r["median_nearest_neighbour_deg"] = float(np.median(nn))
    t = logfire[r["trace_id"]]
    r["lf_cost"] = t["cost_usd"]
    r["lf_requests"] = t["model_requests"]
    r["lf_input"] = t["input_tokens"]
    r["lf_cached"] = t["cached_tokens"]
    r["lf_uncached"] = t["input_tokens"] - t["cached_tokens"]
    r["lf_output"] = t["output_tokens"]
    r["cost_uncached"] = r["lf_uncached"] * RATE_UNCACHED
    r["cost_cached"] = r["lf_cached"] * RATE_CACHED
    r["cost_output"] = r["lf_output"] * RATE_OUTPUT
    assert abs(r["cost_uncached"] + r["cost_cached"] + r["cost_output"] - r["lf_cost"]) < 0.01, label(r)
    r["cost_per_eval"] = r["lf_cost"] / 60.0
    main = (r["usage_split"] or {}).get("main") or {}
    r["main_cost"] = main.get("cost_usd") if r["arm"] == "Standard" else r["lf_cost"]
    r["specialist_cost"] = r["lf_cost"] - r["main_cost"] if r["arm"] == "Standard" else 0.0
    r["main_requests"] = main.get("request_count") if r["arm"] == "Standard" else r["lf_requests"]

# ---------- reference-geometry offsets from shared evaluation points ----------
pairs = []
for a, b in itertools.combinations(runs, 2):
    diffs = []
    for e1, p1 in zip(a["energies"], a["params"]):
        for e2, p2 in zip(b["energies"], b["params"]):
            if max(angdiff(p1[k], p2[k]) for k in p1) <= 0.5 and max(e1, e2) < -233.0:
                diffs.append((e1 - e2) * K)
    if diffs:
        pairs.append({"a": label(a), "b": label(b), "n": len(diffs), "median_kcal": float(np.median(diffs)),
                      "spread_kcal": float(np.max(diffs) - np.min(diffs))})
usable = [p for p in pairs if p["n"] >= 2]
names = [label(r) for r in runs]
connected = {f"{REFERENCE_RUN[0]} r{REFERENCE_RUN[1]}"}
changed = True
while changed:
    changed = False
    for p in usable:
        if (p["a"] in connected) != (p["b"] in connected):
            connected |= {p["a"], p["b"]}
            changed = True
idx = {n: i for i, n in enumerate(sorted(connected))}
rows, rhs, w = [], [], []
for p in usable:
    if p["a"] in idx and p["b"] in idx:
        row = np.zeros(len(idx)); row[idx[p["a"]]] = 1; row[idx[p["b"]]] = -1
        rows.append(row); rhs.append(p["median_kcal"]); w.append(np.sqrt(p["n"]))
row = np.zeros(len(idx)); row[idx[f"{REFERENCE_RUN[0]} r{REFERENCE_RUN[1]}"]] = 1
rows.append(row * 100); rhs.append(0.0); w.append(1.0)
A = np.asarray(rows) * np.asarray(w)[:, None]
sol, *_ = np.linalg.lstsq(A, np.asarray(rhs) * np.asarray(w), rcond=None)
offsets = {n: float(sol[i]) for n, i in idx.items()}
resid = [abs(offsets[p["a"]] - offsets[p["b"]] - p["median_kcal"]) for p in usable if p["a"] in idx and p["b"] in idx]
for r in runs:
    off = offsets.get(label(r))
    r["offset_kcal"] = off
    r["aligned_best"] = None if off is None else r["bsf"][-1] - off / K
aligned_min = min(r["aligned_best"] for r in runs if r["aligned_best"] is not None)
raw_min = min(r["bsf"][-1] for r in runs)
for r in runs:
    r["raw_gap_kcal"] = (r["bsf"][-1] - raw_min) * K
    if r["offset_kcal"] is None:
        r["aligned_gap_kcal"] = None
        r["aligned_regret_curve"] = None
        r["aligned_mean_regret_kcal"] = None
    else:
        curve = (np.asarray(r["bsf"]) - r["offset_kcal"] / K - aligned_min) * K
        r["aligned_gap_kcal"] = float(curve[-1])
        r["aligned_regret_curve"] = curve.tolist()
        r["aligned_mean_regret_kcal"] = float(np.trapezoid(curve, dx=1) / 59)
    bp = r["best_params"]
    r["best_conformer"] = f"({bp['cccc']:.0f}, {bp['ccco']:.0f}, {bp['ccoh']:.0f})"

# ---------- context: 9/23 aligned set (clean repeats) and August 8/17 ----------
context = {}
arm_of = {"main_agent_script_bo_mcp": "Main-script", "main_agent_script_no_bo_mcp": "Local-BO",
          "standard_subagent_script_bo_mcp": "Standard", "main_agent_tool_passing_bo_mcp": "Tool-loop"}
c923 = {a: [] for a in ARMS}
for m in sorted(Path("/local-scratch/home/lynnfang00/research/archive/dihedral-runs-aligned-2026-09-23").glob("dihedral_*Z/repeat_*/cases/dihedral/metrics.json")):
    j = json.loads(m.read_text())
    arm = arm_of[j["architecture"]["architecture_mode"]]
    src = j.get("local_artifacts") if arm == "Local-BO" else j["bo_mcp"]
    bsf = np.asarray(src["best_so_far_by_evaluation"], dtype=float)
    if len(bsf) < 60 or src.get("attempted_objective_evaluations") != 60:
        continue
    q = (bsf[0] - bsf) / (bsf[0] - bsf[-1]) if bsf[0] > bsf[-1] else np.ones_like(bsf)
    c923[arm].append({"auc10": float(np.trapezoid(q[:10]) / 9), "auc30": float(np.trapezoid(q[:30]) / 29),
                      "auc60": float(np.trapezoid(q[:60]) / 59), "best": float(bsf[-1]), "cost": j["agent"]["cost_usd"]})
aug = json.loads(Path("/local-scratch/home/lynnfang00/research/archive/dihedral_clean_prompt_comparison_2026-08-17/data/architecture_summary.json").read_text())
aug_name = {"Standard": "Specialist-script", "Main-script": "Main-script", "Tool-loop": "Tool-loop", "Local-BO": "Local-BO"}
for a in ARMS:
    g = c923[a]
    context[a] = {
        "sep23_n": len(g),
        "sep23_auc10": float(np.mean([x["auc10"] for x in g])) if g else None,
        "sep23_auc30": float(np.mean([x["auc30"] for x in g])) if g else None,
        "sep23_best": float(min(x["best"] for x in g)) if g else None,
        "sep23_cost": float(np.mean([x["cost"] for x in g])) if g else None,
        "aug_auc10": aug[aug_name[a]]["mean_auc10"], "aug_auc10_n": aug[aug_name[a]]["auc10_n"],
        "aug_auc30": aug[aug_name[a]]["mean_auc30"], "aug_auc30_n": aug[aug_name[a]]["auc30_n"],
        "aug_complete": aug[aug_name[a]]["complete_60_result_runs"],
    }

# ---------- arm summaries ----------
def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "sd": None, "min": None, "max": None, "n": 0}
    return {"mean": float(np.mean(vals)), "sd": float(np.std(vals, ddof=1)) if len(vals) > 1 else None,
            "min": float(np.min(vals)), "max": float(np.max(vals)), "n": len(vals)}

summary_arms = {}
for a in ARMS:
    g = [r for r in runs if r["arm"] == a]
    summary_arms[a] = {f: stats([r[f] for r in g]) for f in (
        "auc10", "auc30", "auc60", "mbsf60", "evals_to_90pct", "evals_to_best", "improvement_kcal",
        "raw_gap_kcal", "aligned_gap_kcal", "aligned_mean_regret_kcal", "lf_cost", "cost_per_eval",
        "lf_requests", "tool_calls", "runtime_s", "lf_input", "lf_cached", "lf_uncached", "lf_output",
        "frac_within_1kcal_of_own_best", "median_gap_to_own_best_kcal", "distinct_30deg_cells",
        "median_nearest_neighbour_deg", "main_cost", "specialist_cost")}
    summary_arms[a]["best_raw"] = float(min(r["bsf"][-1] for r in g))
    summary_arms[a]["clean"] = sum(1 for r in g if r["clean"])

# ---------- figures ----------
def arm_legend(ax, loc="best", **kw):
    handles = [plt.Line2D([], [], color=COLOR[a], marker=MARKER[a], linestyle="none", markersize=6, label=a) for a in ARMS]
    ax.legend(handles=handles, loc=loc, fontsize=8, handletextpad=0.3, **kw)


def dotplot(ax, field, ylabel, title, fmt="{:.2f}", lower_better=None, exclude=None, mean_label=True):
    for i, a in enumerate(ARMS):
        g = [r for r in runs if r["arm"] == a and r[field] is not None and not (exclude and exclude(r))]
        xs = i + np.array([-0.13, 0.0, 0.13])[: len(g)]
        ys = [r[field] for r in g]
        ax.scatter(xs, ys, s=34, color=COLOR[a], marker=MARKER[a], edgecolor="white", linewidth=0.8, zorder=3)
        if ys:
            m = float(np.mean(ys))
            ax.hlines(m, i - 0.28, i + 0.28, color=INK, linewidth=1.4, zorder=4)
            if mean_label:
                ax.annotate(fmt.format(m), (i + 0.30, m), xytext=(0, 2), textcoords="offset points", fontsize=7.5, color=INK2, va="bottom")
    ax.set_xticks(range(len(ARMS)), ARMS)
    ax.set_xlim(-0.6, len(ARMS) - 0.25)
    if lower_better is not None:
        ylabel = f"{ylabel}\n({'lower' if lower_better else 'higher'} is better)"
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left")
    ax.grid(axis="x", visible=False)


# F1 best-so-far trajectories (raw energy), small multiples
fig, axes = plt.subplots(1, 4, figsize=(11, 3.3), sharey=True)
ref = -233.1875
for ax, a in zip(axes, ARMS):
    for r in [r for r in runs if r["arm"] == a]:
        y = (np.asarray(r["bsf"]) - ref) * K
        ax.plot(range(1, 61), y, color=COLOR[a], linestyle=LINESTYLE[r["repeat"]], linewidth=1.6, label=f"r{r['repeat']}")
    ax.set_title(a, loc="left")
    ax.set_xlabel("Evaluation")
    ax.set_xlim(1, 60)
    ax.set_yscale("symlog", linthresh=1)
    ax.legend(fontsize=7.5, loc="upper right", handlelength=2.4)
axes[0].set_ylabel("Best-so-far energy\nkcal/mol above -233.1875 Ha")
save(fig, "f1_best_so_far_raw.png")

# F2 within-run normalized convergence
fig, axes = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [1.15, 1]})
ax = axes[0]
for r in runs:
    ax.plot(range(1, 61), r["q"], color=COLOR[r["arm"]], linewidth=0.8, alpha=0.35)
for a in ARMS:
    m = np.mean([r["q"] for r in runs if r["arm"] == a], axis=0)
    ax.plot(range(1, 61), m, color=COLOR[a], linewidth=2.2)
ax.legend(handles=[plt.Line2D([], [], color=COLOR[a], linewidth=2.2, label=a) for a in ARMS], loc="lower right", fontsize=8)
ax.set_xlim(1, 60)
ax.set_ylim(-0.02, 1.04)
ax.set_xlabel("Evaluation")
ax.set_ylabel("Fraction of the run's own improvement\nrealized so far (q)")
ax.set_title("Normalized convergence q(t)", loc="left")
for x in (10, 30):
    ax.axvline(x, color=MUTED, linewidth=0.8, linestyle=(0, (2, 2)))
    ax.text(x + 0.5, 0.03, f"@{x}", fontsize=7.5, color=MUTED)
ax = axes[1]
w = 0.26
for i, a in enumerate(ARMS):
    for j, h in enumerate((10, 30, 60)):
        vals = [r[f"auc{h}"] for r in runs if r["arm"] == a]
        x = i + (j - 1) * w
        ax.bar(x, np.mean(vals), width=w - 0.04, color=COLOR[a], alpha=[0.45, 0.75, 1.0][j], edgecolor="white", linewidth=1.0)
        ax.scatter([x] * len(vals), vals, s=10, color=INK, zorder=3)
        ax.text(x, -0.07, f"@{h}", ha="center", fontsize=6.5, color=INK2)
ax.set_xticks(range(len(ARMS)), ARMS)
ax.tick_params(axis="x", pad=11)
ax.set_ylim(0, 1.05)
ax.set_ylabel("Normalized AUC (higher = faster)")
ax.set_title("Normalized AUC at 10, 30 and 60 evaluations", loc="left")
ax.grid(axis="x", visible=False)
save(fig, "f2_normalized_convergence.png")

# F3 final quality: raw gap and reference-aligned gap
fig, axes = plt.subplots(1, 2, figsize=(11, 3.3))
dotplot(axes[0], "raw_gap_kcal", "kcal/mol above lowest raw best", "Raw final best", lower_better=True)
dotplot(axes[1], "aligned_gap_kcal", "kcal/mol above lowest aligned best", "Final best, aligned to one reference geometry", lower_better=True)
axes[1].text(3, 0.05, "r1, r3: not\nalignable", fontsize=7, color=MUTED, ha="center", va="bottom")
save(fig, "f3_final_quality.png")

# F4 reference offsets
fig, ax = plt.subplots(figsize=(11, 2.9))
for i, r in enumerate(runs):
    if r["offset_kcal"] is None:
        ax.text(i, 0.02, "n/a", ha="center", fontsize=7.5, color=MUTED)
        continue
    v = r["offset_kcal"]
    ax.bar(i, v, color=COLOR[r["arm"]], width=0.62, edgecolor="white")
    txt = "0.00" if abs(v) < 0.005 else f"{v:+.2f}"
    if v < -0.1:
        ax.text(i, v + 0.04, txt, ha="center", va="bottom", fontsize=7, color="white", fontweight="bold")
    else:
        ax.text(i, max(v, 0) + 0.03, txt, ha="center", va="bottom", fontsize=7, color=INK2)
ax.axhline(0, color=MUTED, linewidth=0.8)
ax.set_xticks(range(len(runs)), [f"{r['arm']}\nr{r['repeat']}" for r in runs], fontsize=7.5)
ax.set_ylabel("Energy offset vs Standard r1\nat identical angles (kcal/mol)")
ax.set_ylim(-0.6, 0.45)
ax.set_title("Reference-geometry offsets estimated from shared evaluation points", loc="left")
ax.grid(axis="x", visible=False)
save(fig, "f4_reference_offsets.png")

# F5 cost and efficiency, four panels
fig, axes = plt.subplots(2, 2, figsize=(11, 6.2))
fig.subplots_adjust(wspace=0.28, hspace=0.42)
axes = axes.ravel()
dotplot(axes[0], "lf_cost", "USD per repeat", "Model cost", fmt="${:.2f}", lower_better=True)
dotplot(axes[1], "lf_requests", "model requests", "Model requests", fmt="{:.0f}", lower_better=True)
dotplot(axes[2], "runtime_s", "seconds", "Agent wall time", fmt="{:.0f}", lower_better=True)
for r in runs:
    r["lf_input_m"] = r["lf_input"] / 1e6
dotplot(axes[3], "lf_input_m", "million tokens", "Input tokens (incl. cached)", fmt="{:.1f}", lower_better=True)
save(fig, "f5_cost_efficiency.png")

# F6 cost vs convergence
fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
for ax, field, title in ((axes[0], "auc30", "AUC@30 (higher = faster)"), (axes[1], "aligned_mean_regret_kcal", "Mean aligned regret, kcal/mol (lower = better)")):
    for r in runs:
        if r[field] is None:
            continue
        ax.scatter(r["lf_cost"], r[field], s=46, color=COLOR[r["arm"]], marker=MARKER[r["arm"]], edgecolor="white", linewidth=0.8, zorder=3)
        ax.annotate(f"r{r['repeat']}", (r["lf_cost"], r[field]), xytext=(5, -9) if r["repeat"] == 1 else (5, 3), textcoords="offset points", fontsize=6.5, color=INK2)
    ax.set_xlabel("Model cost per repeat (USD)")
    ax.set_title(title, loc="left")
    arm_legend(ax, loc="best")
save(fig, "f6_cost_vs_quality.png")

# F7 exploration: angle coverage, small multiples (C-C-C-O vs C-C-O-H)
fig, axes = plt.subplots(1, 4, figsize=(11, 3.0), sharex=True, sharey=True)
for ax, a in zip(axes, ARMS):
    for r in [r for r in runs if r["arm"] == a]:
        xs = [p["ccco"] for p in r["params"]]
        ys = [p["ccoh"] for p in r["params"]]
        ax.scatter(xs, ys, s=10, color=COLOR[a], marker=MARKER[a], alpha=0.55, linewidth=0)
        bp = r["best_params"]
        ax.scatter([bp["ccco"]], [bp["ccoh"]], s=42, facecolor="none", edgecolor=INK, linewidth=1.0, zorder=4)
    ax.set_title(a, loc="left")
    ax.set_xlim(-185, 185); ax.set_ylim(-185, 185)
    ax.set_xticks([-180, -90, 0, 90, 180]); ax.set_yticks([-180, -90, 0, 90, 180])
    ax.set_xlabel("C-C-C-O angle (deg)")
axes[0].set_ylabel("C-C-O-H angle (deg)")
save(fig, "f7_exploration_angles.png")

# F8 exploration metrics
fig, axes = plt.subplots(1, 3, figsize=(11, 3.0))
fig.subplots_adjust(wspace=0.38)
dotplot(axes[0], "frac_within_1kcal_of_own_best", "fraction of 60 evaluations", "Share within 1 kcal/mol of own best", fmt="{:.2f}")
dotplot(axes[1], "distinct_30deg_cells", "of 60 evaluations", "Distinct 30-degree angle cells", fmt="{:.0f}")
dotplot(axes[2], "evals_to_90pct", "evaluation index", "Evaluations to 90% of improvement", fmt="{:.0f}", lower_better=True)
for ax in axes:
    ax.tick_params(axis="x", labelsize=7.5, rotation=20)
save(fig, "f8_exploration_metrics.png")

# ---------- write summary ----------
out_runs = []
for r in runs:
    out_runs.append({k: v for k, v in r.items() if k not in ("energies", "params", "best_so_far", "usage_split", "tool_counts")})
(DATA / "summary.json").write_text(json.dumps({
    "runs": out_runs, "arms": summary_arms, "context": context,
    "offsets": {"reference": f"{REFERENCE_RUN[0]} r{REFERENCE_RUN[1]}", "by_run": offsets,
                "pairs": pairs, "max_residual_kcal": float(max(resid)) if resid else None,
                "aligned_min_hartree": aligned_min, "raw_min_hartree": raw_min},
}, indent=1))
print("figures:", sorted(p.name for p in FIG.glob("*.png")))
print("offsets:", {k: round(v, 3) for k, v in offsets.items()}, "max residual", round(max(resid), 4))
for a in ARMS:
    s = summary_arms[a]
    print(f"{a:12s} AUC10 {s['auc10']['mean']:.3f} AUC30 {s['auc30']['mean']:.3f} AUC60 {s['auc60']['mean']:.3f} "
          f"cost {s['lf_cost']['mean']:.2f} req {s['lf_requests']['mean']:.0f} rt {s['runtime_s']['mean']:.0f} "
          f"rawgap {s['raw_gap_kcal']['mean']:.2f} aligned {s['aligned_gap_kcal']['mean'] if s['aligned_gap_kcal']['mean'] is not None else 'n/a'}")
print("context:", json.dumps(context)[:600])
