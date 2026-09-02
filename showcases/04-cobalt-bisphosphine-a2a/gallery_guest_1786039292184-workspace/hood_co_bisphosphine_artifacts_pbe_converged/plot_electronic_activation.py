#!/usr/bin/env python3
"""Plot electronic activation from campaign evaluations.jsonl.

Shows per-evaluation electronic_activation values, marks feasible vs infeasible
hard-penalized results, and overlays the cumulative best among feasible points.
"""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

base = Path(__file__).resolve().parent
inp = base / 'evaluations.jsonl'
rows = []
for i, line in enumerate(inp.read_text().splitlines(), start=1):
    if not line.strip():
        continue
    r = json.loads(line)
    cand = (r.get('candidate') or {}).get('candidate_id') or r.get('candidate_id') or f'row_{i}'
    obj = r.get('objectives') or {}
    rows.append({
        'iteration': len(rows) + 1,
        'candidate': cand,
        'phase': r.get('phase') or '',
        'feasible': bool(r.get('feasible')),
        'electronic_activation': float(obj.get('electronic_activation')),
    })

if not rows:
    raise SystemExit('No rows found in evaluations.jsonl')

df = pd.DataFrame(rows)
# Cumulative best only over feasible points. Infeasible hard penalties do not update best.
best = []
cur = None
for _, row in df.iterrows():
    if row['feasible']:
        cur = row['electronic_activation'] if cur is None else max(cur, row['electronic_activation'])
    best.append(cur)
df['best_feasible_electronic_activation_so_far'] = best

out_csv = base / 'electronic_activation_curve.csv'
df.to_csv(out_csv, index=False)

fig, ax = plt.subplots(figsize=(10, 5.5))
feas = df[df['feasible']]
fail = df[~df['feasible']]

if not feas.empty:
    ax.scatter(feas['iteration'], feas['electronic_activation'], s=80, color='#2ca02c', edgecolor='black', label='Feasible evaluation', zorder=3)
if not fail.empty:
    ax.scatter(fail['iteration'], fail['electronic_activation'], s=90, marker='x', color='#d62728', linewidth=2, label='Infeasible / hard penalty', zorder=3)

# Connect all raw values lightly for chronology.
ax.plot(df['iteration'], df['electronic_activation'], color='0.65', lw=1, zorder=1)
# Best feasible curve.
best_plot = df.dropna(subset=['best_feasible_electronic_activation_so_far'])
if not best_plot.empty:
    ax.step(best_plot['iteration'], best_plot['best_feasible_electronic_activation_so_far'], where='post', color='#1f77b4', lw=2.5, label='Best feasible so far')

# Warm-start/BO separator: first four are warm-start in this campaign.
if len(df) > 4:
    ax.axvline(4.5, ls='--', color='0.35', lw=1.2)
    ax.text(4.55, ax.get_ylim()[0], 'BO takes over', rotation=90, va='bottom', ha='left', color='0.25')

for _, row in feas.iterrows():
    ax.annotate(row['candidate'], (row['iteration'], row['electronic_activation']), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=8, rotation=20)

ax.set_title('Electronic activation over campaign evaluations\nPBE/def2-SVP strict-convergence campaign')
ax.set_xlabel('Evaluation number')
ax.set_ylabel('electronic_activation objective (maximize)')
ax.grid(alpha=0.3)
ax.legend(loc='best')
fig.tight_layout()
out_png = base / 'electronic_activation_curve.png'
fig.savefig(out_png, dpi=180)
plt.close(fig)

print(f'Wrote {out_png}')
print(f'Wrote {out_csv}')
print(df.to_string(index=False))
