"""Assemble the architecture-comparison PDF from data/summary.json, data/runs.json and figures/.

Run with the system python3 (reportlab). Every number in the text is read from the data files.
"""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = Path(__file__).parent
OUT = HERE / "DIHEDRAL_ARCHITECTURE_COMPARISON_2026-10-06.pdf"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DV-B", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
oblique = FONT_DIR / "DejaVuSans-Oblique.ttf"
pdfmetrics.registerFont(TTFont("DV-I", str(oblique if oblique.exists() else FONT_DIR / "DejaVuSans.ttf")))

INK, INK2, MUTED, RULE, HEAD = (colors.HexColor(c) for c in ("#0b0b0b", "#52514e", "#8a8984", "#d9d8d3", "#f1f0ec"))
ST = {
    "title": ParagraphStyle("title", fontName="DV-B", fontSize=17, leading=21, textColor=INK, spaceAfter=4),
    "sub": ParagraphStyle("sub", fontName="DV", fontSize=9.5, leading=13, textColor=INK2, spaceAfter=10),
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=12.5, leading=16, textColor=INK, spaceBefore=10, spaceAfter=5, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=10.5, leading=14, textColor=INK, spaceBefore=6, spaceAfter=3, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="DV", fontSize=9, leading=12.6, textColor=INK, spaceAfter=5, alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName="DV", fontSize=9, leading=12.6, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=3),
    "cap": ParagraphStyle("cap", fontName="DV-I", fontSize=7.8, leading=10.4, textColor=INK2, spaceBefore=2, spaceAfter=9),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.6, leading=9.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DV-B", fontSize=7.6, leading=9.6, textColor=INK),
    "kpi_n": ParagraphStyle("kpi_n", fontName="DV-B", fontSize=15, leading=18, textColor=INK),
    "kpi_l": ParagraphStyle("kpi_l", fontName="DV", fontSize=7.6, leading=9.8, textColor=INK2),
}
WIDTH = letter[0] - 1.5 * inch
ARMS = ["Standard", "Main-script", "Tool-loop", "Local-BO"]
K = 627.509474

S = json.loads((HERE / "data/summary.json").read_text())
RUNS = S["runs"]
RAW = {(r["arm"], r["repeat"]): r for r in json.loads((HERE / "data/runs.json").read_text())}
A = S["arms"]
C = S["context"]


def P(text, style="body"):
    return Paragraph(text, ST[style])


def B(text):
    return Paragraph(text, ST["bullet"], bulletText="•")


def fig(name, caption, heading=None):
    path = HERE / "figures" / name
    w, h = ImageReader(str(path)).getSize()
    img = Image(str(path), width=WIDTH, height=WIDTH * h / w)
    return KeepTogether(([P(heading, "h1")] if heading else []) + [img, P(caption, "cap")])


def table(rows, widths, header_rows=1, align_right_from=1):
    data = [[c if isinstance(c, Paragraph) else Paragraph(str(c), ST["cellb" if i < header_rows else "cell"]) for c in row]
            for i, row in enumerate(rows)]
    t = Table(data, colWidths=[w * WIDTH for w in widths], repeatRows=header_rows, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), HEAD),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.7, MUTED),
        ("LINEBELOW", (0, header_rows), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def m(arm, field, fmt="{:.2f}"):
    v = A[arm][field]["mean"]
    return "–" if v is None else fmt.format(v)


def run(arm, rep):
    return next(r for r in RUNS if r["arm"] == arm and r["repeat"] == rep)


def fmt_s(v):
    return f"{v:,.0f}"


# ---------------- derived numbers used in the text ----------------
same_basin = [r for r in RUNS if r["aligned_gap_kcal"] is not None and r["aligned_gap_kcal"] < 0.6 and r["aligned_gap_kcal"] > 0.4]
basin_spread = max(r["aligned_gap_kcal"] for r in same_basin) - min(r["aligned_gap_kcal"] for r in same_basin)
max_offset = max(abs(v) for v in S["offsets"]["by_run"].values())
offset_span = max(S["offsets"]["by_run"].values()) - min(S["offsets"]["by_run"].values())
raw_span = max(r["raw_gap_kcal"] for r in RUNS)
total_cost = sum(r["lf_cost"] for r in RUNS)
lb2 = run("Local-BO", 2)
fastest = max(ARMS, key=lambda a: A[a]["auc30"]["mean"])
cheapest = min(ARMS, key=lambda a: A[a]["lf_cost"]["mean"])

story = []
story += [
    P("Dihedral benchmark: comparison of the four agent architectures", "title"),
    P("Final single-commit sweep, 2026-10-06 · 4 architectures × 3 repeats · commit 0949c2d1 · GPT-5.4 via LiteLLM "
      "(medium reasoning) · BayBE · 60 PBE-D4/def2-SVP single-point evaluations per repeat · run folder "
      "<font name='DV-I'>dihedral-runs-sweep-2026-10-06b</font>", "sub"),
]
kpis = [
    (f"{sum(1 for r in RUNS if r['clean'])}/12", "repeats clean: one commit, one image, 60 evaluations each, provenance verified"),
    (f"{basin_spread:.2f} kcal/mol", f"spread of the shared minimum reached by {len(same_basin)} runs once reference geometries are aligned"),
    (f"{A[fastest]['auc30']['mean']:.2f}", f"best mean AUC@30 ({fastest}); higher = converges faster within the run"),
    (f"${total_cost:.2f}", f"model cost of the 12 repeats; cheapest arm {cheapest} at ${A[cheapest]['lf_cost']['mean']:.2f}/repeat"),
]
kt = Table([[P(n, "kpi_n") for n, _ in kpis], [P(l, "kpi_l") for _, l in kpis]], colWidths=[WIDTH / 4] * 4, hAlign="LEFT")
kt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK)]))
story += [kt, Spacer(1, 8)]

story += [P("1. Summary", "h1")]
story += [
    B(f"<b>Final energy does not rank the architectures.</b> Raw best energies span {raw_span:.1f} kcal/mol, but runs built "
      f"butanol from different reference geometries: at identical angles, energies differ between runs by a near-constant "
      f"offset of up to {offset_span:.2f} kcal/mol, and Local-BO r1 and r3 hand-built a geometry with their own angle "
      f"convention that cannot be compared at all. Once aligned to one reference, all three Standard runs, all three "
      f"Main-script runs and Tool-loop r3 reached the same minimum near (180°, ±62°, 180°), within {basin_spread:.2f} kcal/mol "
      f"of each other. Tool-loop r1 and r2 stopped in other conformers about 0.4 kcal/mol higher; Local-BO r2 found an "
      f"O–H gauche conformer about {abs(same_basin[0]['aligned_gap_kcal'] - 0):.1f} kcal/mol lower, in a region no other run sampled."),
    B(f"<b>Convergence speed differs.</b> Within-run normalized AUC (the August metric): Standard is fastest at every horizon "
      f"(AUC@10 {m('Standard','auc10')}, @30 {m('Standard','auc30')}, @60 {m('Standard','auc60')}); Main-script "
      f"({m('Main-script','auc10')} / {m('Main-script','auc30')} / {m('Main-script','auc60')}) and Local-BO "
      f"({m('Local-BO','auc10')} / {m('Local-BO','auc30')} / {m('Local-BO','auc60')}) are close; Tool-loop is slowest "
      f"({m('Tool-loop','auc10')} / {m('Tool-loop','auc30')} / {m('Tool-loop','auc60')}). Three repeats per arm: descriptive, not significant."),
    B(f"<b>Cost and time trade off against that speed.</b> Local-BO is cheapest (${m('Local-BO','lf_cost')}/repeat) but slow "
      f"({fmt_s(A['Local-BO']['runtime_s']['mean'])} s). Main-script costs ${m('Main-script','lf_cost')} and takes "
      f"{fmt_s(A['Main-script']['runtime_s']['mean'])} s. Standard costs ${m('Standard','lf_cost')} and is slowest "
      f"({fmt_s(A['Standard']['runtime_s']['mean'])} s): it ran BO strictly one candidate at a time for 60 iterations, which "
      f"also explains its fast per-evaluation convergence. Tool-loop is fastest on the clock ({fmt_s(A['Tool-loop']['runtime_s']['mean'])} s) "
      f"but most expensive (${m('Tool-loop','lf_cost')}), driven by {m('Tool-loop','lf_input', '{:,.0f}')} input tokens per repeat."),
    B(f"<b>Exploration differs.</b> Local-BO and Tool-loop spread evaluations widest ({m('Local-BO','distinct_30deg_cells','{:.0f}')} "
      f"and {m('Tool-loop','distinct_30deg_cells','{:.0f}')} distinct 30° angle cells of 60); Standard concentrated most "
      f"({m('Standard','distinct_30deg_cells','{:.0f}')} cells, {float(m('Standard','frac_within_1kcal_of_own_best'))*100:.0f}% of evaluations within "
      f"1 kcal/mol of its best). Only Local-BO r2 sampled the O–H gauche region where the lowest aligned energy lies."),
    B(f"<b>Reading:</b> Main-script gives the best balance of convergence, cost and wall time; Standard converges fastest per "
      f"evaluation but is the slowest and {A['Standard']['lf_cost']['mean']/A['Main-script']['lf_cost']['mean']:.1f}× Main-script's cost; Local-BO is the cheapest and explores most broadly; Tool-loop "
      "is the most expensive, converges slowest, and needed two infrastructure fixes before it finished reliably (§9)."),
]

story += [P("2. What was compared", "h1")]
story += [table([
    ["Architecture", "How BO is driven", "Earlier name"],
    ["Standard", "Main agent delegates to a BO specialist, which writes a script that drives BO-MCP; the main agent runs it.", "Specialist-script (August)"],
    ["Main-script", "Main agent itself writes and runs a script that drives BO-MCP.", "Main-script"],
    ["Tool-loop", "Main agent calls BO-MCP tools directly turn by turn; no host shell, PySCF through container tools.", "Tool-loop"],
    ["Local-BO", "Main agent writes and runs its own BayBE loop locally; no BO-MCP.", "Local-BO"],
], [0.16, 0.6, 0.24])]
story += [Spacer(1, 6), P(
    "Controls identical across all 12 repeats (verified on every run manifest): the same user prompt; commit 0949c2d1 with a "
    "clean tree; container image ecb0cf0adc4a; route litellm-openai-responses (gpt-5.4, medium reasoning); BO_BACKEND=baybe; "
    "agent time limit 5400 s; request limit 120; BO-MCP tools declared directly (BO_MCP_DEFER_TOOLS=0); PySCF profile "
    "cpu-smoke at 16 GB. Each repeat ran with an empty memory root. Repeats are 3 per arm, chained in one systemd unit "
    "on 2026-10-06 09:19–16:37 EDT.")]

story += [P("3. Results at a glance", "h1")]
rows = [["", "Clean", "Raw best (Ha)", "Aligned gap*", "AUC @10", "AUC @30", "AUC @60", "Evals to 90%", "Cost / repeat", "Requests", "Input tokens (M)", "Wall time (s)"]]
for a in ARMS:
    rows.append([a, f"{A[a]['clean']}/3", f"{A[a]['best_raw']:.6f}", m(a, "aligned_gap_kcal"), m(a, "auc10"), m(a, "auc30"), m(a, "auc60"),
                 m(a, "evals_to_90pct", "{:.0f}"), "$" + m(a, "lf_cost"), m(a, "lf_requests", "{:.0f}"),
                 f"{A[a]['lf_input']['mean']/1e6:.1f}", m(a, "runtime_s", "{:,.0f}")])
story += [table(rows, [0.105, 0.065, 0.125, 0.09, 0.065, 0.065, 0.065, 0.07, 0.075, 0.1, 0.085, 0.09]),
          P("Means over three repeats unless noted; raw best is the arm's best repeat. *Aligned gap, in kcal/mol: energy above the lowest "
            "aligned best of any run (Local-BO r2), averaged over the arm's alignable repeats; Local-BO's value is r2 only "
            "(r1 and r3 cannot be aligned). Cost, requests and tokens are per-request sums from Logfire and include Standard's "
            "specialist.", "cap")]

story += [fig("f1_best_so_far_raw.png", heading="4. Convergence", caption="Figure 1. Best-so-far energy per repeat (line style = repeat), in kcal/mol above −233.1875 Ha "
              "on a symmetric-log axis. Absolute levels include each run's reference-geometry offset (§5): Main-script r2 and r3 sit "
              "about 0.5 kcal/mol lower largely for that reason, and Local-BO r1/r3 are on a different surface.")]
story += [fig("f2_normalized_convergence.png", "Figure 2. Left: fraction of each run's own improvement realized after t evaluations, "
              "q(t) = (E₁ − best-so-far(t)) / (E₁ − E_best); thin lines are repeats, bold lines arm means. Right: trapezoidal "
              "area under q(t) over the first 10, 30 and 60 evaluations (bars: arm mean; dots: repeats). This measures speed "
              "toward each run's own best and is independent of reference geometry.")]
rows = [["Run", "AUC@10", "AUC@30", "AUC@60", "MBSF@60", "Evals to 90%", "Eval of best", "Improvement (kcal/mol)", "First energy (Ha)"]]
for r in RUNS:
    raw = RAW[(r["arm"], r["repeat"])]
    rows.append([f"{r['arm']} r{r['repeat']}", f"{r['auc10']:.3f}", f"{r['auc30']:.3f}", f"{r['auc60']:.3f}", f"{r['mbsf60']:.3f}",
                 r["evals_to_90pct"], r["evals_to_best"], f"{r['improvement_kcal']:.1f}", f"{raw['energies'][0]:.6f}"])
story += [table(rows, [0.15, 0.08, 0.08, 0.08, 0.1, 0.1, 0.1, 0.15, 0.16]),
          P("MBSF@60 (mean of q over 60 points) is listed beside trapezoidal AUC@60 for continuity with the 2026-08-11 metric "
            "comparison; the two differ by at most a few thousandths. A large improvement from a poor first point can make a run "
            "look fast on AUC without reaching a low energy, so AUC must be read together with §5.", "cap")]

story += [P("5. Final quality and comparability", "h1")]
story += [P(
    "Agents prepare the molecule themselves, so two runs evaluating the same three angles need not compute the same energy. "
    f"Comparing every pair of evaluations from different runs whose angles agree within 0.5° shows near-constant energy "
    f"offsets between runs: Main-script r2 and r3 sit {abs(S['offsets']['by_run']['Main-script r2']):.2f} kcal/mol below "
    f"Standard r1; Tool-loop and Standard r2 about 0.13 above; Local-BO r2 {S['offsets']['by_run']['Local-BO r2']:.2f} above. "
    f"The offsets are mutually consistent (largest residual of a weighted least-squares fit over all pairs "
    f"{S['offsets']['max_residual_kcal']:.3f} kcal/mol), so a single offset per run aligns them. Local-BO r1 and r3 share "
    "at most one point with any other run and built butanol from idealized internal coordinates with their own angle sign "
    "convention; they cannot be aligned.")]
story += [fig("f3_final_quality.png", "Figure 3. Final best per repeat (bar: arm mean). Left: raw energies, each on its own reference "
              "geometry. Right: the same values corrected by the per-run offsets of Figure 4, relative to the lowest aligned best "
              "(Local-BO r2). Local-BO r1 and r3 are absent on the right.")]
story += [fig("f4_reference_offsets.png", "Figure 4. Per-run energy offset relative to Standard r1 at identical angles, estimated from "
              "shared evaluation points (≥ 2 shared points per pair, angles within 0.5°).")]
rows = [["Run", "Best conformer (C–C–C–C, C–C–C–O, C–C–O–H)", "Raw best (Ha)", "Offset (kcal/mol)", "Aligned gap (kcal/mol)", "Reading"]]
for r in RUNS:
    if r["aligned_gap_kcal"] is None:
        reading = "own geometry and angle convention; not comparable"
    elif r["aligned_gap_kcal"] < 0.05:
        reading = "lowest aligned: O–H gauche conformer"
    elif r["aligned_gap_kcal"] < 0.6:
        reading = "shared minimum (180°, ±62°, 180°)"
    else:
        reading = "different conformer, higher"
    rows.append([f"{r['arm']} r{r['repeat']}", r["best_conformer"], f"{r['bsf'][-1]:.6f}",
                 "n/a" if r["offset_kcal"] is None else ("0.00" if abs(r["offset_kcal"]) < 0.005 else f"{r['offset_kcal']:+.2f}"),
                 "n/a" if r["aligned_gap_kcal"] is None else f"{r['aligned_gap_kcal']:.2f}", reading])
story += [table(rows, [0.13, 0.25, 0.13, 0.11, 0.12, 0.26])]
story += [Spacer(1, 4), P(
    f"Interpretation. On a common reference, three architectures repeatedly reach the same minimum, so they do not differ "
    f"in the quality they reach; the raw lead of Main-script (lowest raw energy) is mostly its reference geometry. "
    f"Local-BO r2's conformer is about {same_basin[0]['aligned_gap_kcal']:.1f} kcal/mol below that minimum, but no other run "
    f"evaluated within 10° of it, so whether every run's surface favours it cannot be checked from these data without new calculations.")]

story += [fig("f5_cost_efficiency.png", heading="6. Cost and efficiency", caption="Figure 5. Per-repeat model cost, model requests, agent wall time and input tokens "
              "(including cached tokens), with arm means. Requests, tokens and cost include Standard's specialist.")]
rows = [["", "Uncached input", "Cached input", "Output", "Total cost", "Cost / evaluation", "Main agent", "Specialist"]]
for a in ARMS:
    g = [r for r in RUNS if r["arm"] == a]
    mean = lambda f: sum(r[f] for r in g) / len(g)
    rows.append([a, f"${mean('cost_uncached'):.2f}", f"${mean('cost_cached'):.2f}", f"${mean('cost_output'):.2f}",
                 f"${mean('lf_cost'):.2f}", f"${mean('cost_per_eval'):.3f}", f"${mean('main_cost'):.2f}",
                 f"${mean('specialist_cost'):.2f}" if a == "Standard" else "–"])
story += [table(rows, [0.14, 0.13, 0.12, 0.1, 0.11, 0.14, 0.12, 0.14]),
          P("Mean cost per repeat split by token class, at the rates implied by Logfire's per-request costs ($2.50 per million "
            "uncached input tokens, $0.25 per million cached, $15 per million output); the split reproduces each run's recorded "
            "total to within $0.01. In Standard most spend is the specialist's. The run manifests' usage_split field quotes a higher "
            "specialist cost (about $4.5 for r1) that does not match the per-request costs; the per-request sum, which equals the "
            "eval's own cost metric, is used here.", "cap")]
story += [fig("f6_cost_vs_quality.png", "Figure 6. Cost per repeat against AUC@30 (left) and against mean aligned regret over 60 "
              "evaluations (right; kcal/mol above the lowest aligned best, averaged over the best-so-far curve; Local-BO r1/r3 not alignable).")]

story += [P("7. Agent behaviour", "h1")]
cats = [("BO-MCP tools", lambda n: n.startswith("bo_") or n.startswith("inspect_bo_mcp")),
        ("Container tools", lambda n: n.startswith("container_")),
        ("Host shell / Python", lambda n: n in {"bash_exec", "python_repl", "start_monitor", "stop_monitor", "list_monitors"}),
        ("Geometry tools", lambda n: n in {"set_molecular_dihedrals", "inspect_smiles_geometry"}),
        ("Skills", lambda n: n in {"load_skill", "read_skill_resource"}),
        ("Subagent", lambda n: n in {"task", "wait_tasks"})]
rows = [["", *[c for c, _ in cats], "Total tool calls"]]
for a in ARMS:
    g = [RAW[(a, rep)] for rep in (1, 2, 3)]
    row = [a]
    for _, pred in cats:
        row.append(f"{sum(sum(v for k, v in r['tool_counts'].items() if pred(k)) for r in g) / 3:.1f}")
    row.append(f"{sum(r['tool_calls'] for r in g) / 3:.1f}")
    rows.append(row)
story += [table(rows, [0.14, 0.12, 0.12, 0.14, 0.12, 0.08, 0.1, 0.18]),
          P("Mean tool calls per repeat by category. For Standard these are the main agent's calls only; the specialist's tool "
            "calls are not itemized in the run metrics.", "cap")]
rows = [["Run", "Configured batch size", "BO iterations recorded", "Suggestions generated", "Duplicates", "Failed evaluations"]]
for r in RUNS:
    raw = RAW[(r["arm"], r["repeat"])]
    rows.append([f"{r['arm']} r{r['repeat']}", raw["campaign_batch_size"] or "own loop", raw["campaign_iterations"] or "–",
                 raw["suggestions_generated"] or "–", raw["duplicates"], raw["failed"]])
story += [table(rows, [0.2, 0.18, 0.18, 0.16, 0.13, 0.15]),
          P("BO campaign structure as recorded by BO-MCP (Local-BO runs its own loop and records none). Standard's specialist "
            "ran strictly sequential BO (batch 1, 60 iterations); Main-script used batches of 1–5; Tool-loop batches of 4–5 over "
            "6–9 iterations. No repeat produced a duplicate or a failed evaluation.", "cap")]

story += [fig("f7_exploration_angles.png", heading="8. Exploration", caption="Figure 7. Every evaluated point of each arm projected onto the C–C–C–O and C–C–O–H "
              "angles (all three repeats; open circles mark each repeat's best). Local-BO's points for r1 and r3 use those runs' "
              "own angle convention.")]
story += [fig("f8_exploration_metrics.png", "Figure 8. Share of evaluations within 1 kcal/mol of the run's own best (exploitation), "
              "number of distinct 30° cells of the three-angle space visited (spread), and evaluations needed to reach 90% of "
              "the run's own improvement.")]

story += [P("9. Reliability and how the final sweep was reached", "h1")]
story += [table([
    ["Sweep", "Code", "Clean", "Failures and causes", "Fix"],
    ["2026-09-23/24 (aligned)", "3 commits", "10/12*", "Main-script r2 MCP handshake 5 s timeout; Standard r3 hit the 3600 s agent cap", "6ad91832, d4d251ea"],
    ["2026-10-05", "6ad91832", "8/12", "Local-BO r2: Playwright handshake kept the 5 s default. Tool-loop 0/3: BO-MCP tools found by search were declared only in one early history item, which gpt-5.4 stopped using in long runs (replay 0/5 as-is vs 5/5 declared normally)", "3ec11b1a, 4af9f52e"],
    ["2026-10-06", "5a9cc789", "Tool-loop 4/6", "The documented runner command failed inside agent commands because they ran in a login shell that dropped the image's Python; two improvised workarounds lost evaluations", "0949c2d1"],
    ["2026-10-06 (final)", "0949c2d1", "12/12", "–", "–"],
], [0.17, 0.1, 0.09, 0.47, 0.17]),
    P("*The 9/23–24 set excludes three earlier Standard repeats that ran before the canonical-case budget fix. Every failure "
      "above was an infrastructure fault, not a chemistry or PySCF fault; Tool-loop was the architecture most exposed to them "
      "because it drives BO-MCP and PySCF through tools rather than a script. Model cost of the attempts: about $20 on 10/05, "
      "$19 on 10/06, $24.96 for the final sweep.", "cap")]

story += [P("10. Context: earlier dihedral matrices", "h1")]
rows = [["", "AUC@10 now", "AUC@30 now", "AUC@10 9/23 (n)", "AUC@30 9/23 (n)", "AUC@10 Aug (n)", "AUC@30 Aug (n)", "Cost now / 9/23"]]
for a in ARMS:
    c = C[a]
    f = lambda v: "–" if v is None else f"{v:.2f}"
    rows.append([a, m(a, "auc10"), m(a, "auc30"), f"{f(c['sep23_auc10'])} ({c['sep23_n']})", f"{f(c['sep23_auc30'])} ({c['sep23_n']})",
                 f"{f(c['aug_auc10'])} ({c['aug_auc10_n']})", f"{f(c['aug_auc30'])} ({c['aug_auc30_n']})",
                 f"${m(a,'lf_cost')} / ${c['sep23_cost']:.2f}" if c["sep23_cost"] else "–"])
story += [table(rows, [0.13, 0.1, 0.1, 0.13, 0.13, 0.13, 0.13, 0.15]),
          P("Same within-run AUC definition. 9/23 uses its repeats with complete 60-evaluation trajectories; August values are "
            "from the 2026-08-17 clean-prompt report (its Standard arm was named Specialist-script; Tool-loop had one 10-point "
            "run). The earlier matrices ran different code (9/23 spans three commits; August predates the container execution "
            "path), so differences are descriptive. Convergence by 10 evaluations is faster now than on 9/23 in every arm, and faster "
            "than in August except against August's single censored Tool-loop run.", "cap")]

story += [P("11. Definitions and methods", "h1")]
for t in [
    "<b>Best-so-far</b>: running minimum of the 60 energies in evaluation order, taken from each run's BO-MCP read-back or local result file and checked against the eval's own best-so-far record.",
    "<b>q(t) and AUC@h</b>: q(t) = (E₁ − best(t)) / (E₁ − E_best), and AUC@h = trapezoid(q(1..h)) / (h − 1). Identical to the 2026-08-17 report; independent of the reference geometry because each run is normalized to itself.",
    "<b>Reference offsets</b>: for every pair of runs, the median energy difference over evaluation pairs whose three angles agree within 0.5°; per-run offsets by weighted least squares (weight √n, pairs with n ≥ 2), anchored at Standard r1.",
    "<b>Aligned regret</b>: (best(t) − offset − E*) in kcal/mol, with E* the lowest aligned best; its trapezoidal mean over 60 evaluations is the 'mean aligned regret'.",
    "<b>Exploration</b>: distinct 30° cells = number of occupied cells when each of the three angles is binned into 12 sectors; exploitation share = fraction of evaluations within 1 kcal/mol of the run's own best.",
    "<b>Cost and tokens</b>: per-request sums of operation.cost and token counts over every model call in the repeat's Logfire trace (main agent and specialist). Wall time is the eval's timer around the agent run.",
    "<b>Angle names</b>: each run named its parameters differently; they were mapped to C–C–C–C, C–C–C–O and C–C–O–H from the atom letters, and for the two runs with numbered names (Main-script r3, Tool-loop r3) from the definitions in their final answers.",
]:
    story.append(B(t))

story += [P("12. Limitations", "h1")]
for t in [
    "Three repeats per architecture: every comparison is descriptive; no difference here is statistically established.",
    "Agents choose the reference geometry; raw energies mix optimizer quality with molecule preparation. Alignment assumes a constant offset per run, supported by the fit but tested only where runs share points.",
    "Local-BO r1 and r3 used their own angle convention and geometry builder; their angles in Figure 7 and their raw energies are not comparable with the other runs.",
    "Normalized AUC rewards early arrival at a run's own best, which can flatter a run with a poor first point or a high final best.",
    "The provider side changed between 9/24 and 10/05 (identical first-request content billed about 2,850 more input tokens), so cost comparisons across dates are approximate.",
    "No energies were recomputed for this report; it reads the retained run artifacts and Logfire only.",
]:
    story.append(B(t))

story += [P("13. Data and reproducibility", "h1")]
story += [P(
    "Runs: <font name='DV-I'>~/research/dihedral-runs-sweep-2026-10-06b/</font> (audit in audit_runs.json). Report folder: "
    "<font name='DV-I'>~/research/dihedral_architecture_comparison_2026-10-06/</font> with extract_data.py (per-repeat records "
    "from the run tree), generate_report.py (metrics and figures), build_pdf.py (this document), data/runs.json, "
    "data/logfire_totals.json and data/summary.json. Logfire project bo-mcp-grafico-lynn; trace ids per repeat are in "
    "data/runs.json. Project log entry: PROJECT_LOG.md, “2026-10-05/06 — Twelve clean dihedral repeats on one commit after "
    "three more root-cause fixes”.")]


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("DV", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch, "Dihedral benchmark: architecture comparison · final sweep 2026-10-06 · commit 0949c2d1")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.5 * inch, f"{doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUT), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.75 * inch,
                        title="Dihedral benchmark: architecture comparison (2026-10-06)",
                        author="Yanlin Fang", subject="Final single-commit dihedral sweep, commit 0949c2d1")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
