#!/usr/bin/env python3
"""Plot electronic activation with a useful y-scale.

Unlike the all-points plot, this excludes hard-penalized infeasible values
(-100) from the y-axis so the decimal-scale differences among feasible
candidates are visible. Infeasible evaluations are shown only as red rug marks
at the bottom of the plot.
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
for line in inp.read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    cand = (r.get('candidate') or {}).get('candidate_id') or r.get('candidate_id') or f'row_{len(rows)+1}'
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
feas = df[df['feasible']].copy()
fail = df[~df['feasible']].copy()
if feas.empty:
    raise SystemExit('No feasible points to plot')

# Cumulative best over feasible values in chronological order.
cur = None
best_vals = []
for _, row in df.iterrows():
    if row['feasible']:
        val = row['electronic_activation']
        cur = val if cur is None else max(cur, val)
    best_vals.append(cur)
df['best_feasible_electronic_activation_so_far'] = best_vals
best_plot = df[df['best_feasible_electronic_activation_so_far'].notna()].copy()

out_csv = base / 'electronic_activation_feasible_only_curve.csv'
df.to_csv(out_csv, index=False)

fig, ax = plt.subplots(figsize=(10.5, 5.8))

# Useful scale from feasible values only.
ymin = feas['electronic_activation'].min()
ymax = feas['electronic_activation'].max()
pad = max(0.025, 0.15 * (ymax - ymin if ymax > ymin else 0.1))
ylo, yhi = ymin - pad, ymax + pad

# Light chronological line connecting only feasible observations.
ax.plot(feas['iteration'], feas['electronic_activation'], color='0.65', lw=1.2, zorder=1)
ax.scatter(
    feas['iteration'], feas['electronic_activation'],
    s=90, color='#2ca02c', edgecolor='black', linewidth=0.7,
    label='Feasible electronic activation', zorder=3,
)
ax.step(
    best_plot['iteration'], best_plot['best_feasible_electronic_activation_so_far'],
    where='post', color='#1f77b4', lw=2.5, label='Best feasible so far', zorder=2,
)

# Show infeasible evaluations as rug marks, not as -100 values that destroy scale.
rug_y = ylo + 0.04 * (yhi - ylo)
if not fail.empty:
    ax.scatter(
        fail['iteration'], [rug_y] * len(fail),
        s=90, marker='x', color='#d62728', linewidth=2,
        label='Infeasible evaluation (not on y-scale)', zorder=4,
    )

# Warm-start / BO divider.
if len(df) > 4:
    ax.axvline(4.5, ls='--', color='0.35', lw=1.2)
    ax.text(4.55, ylo + 0.02*(yhi-ylo), 'BO takes over', rotation=90, va='bottom', ha='left', color='0.25')

for _, row in feas.iterrows():
    ax.annotate(
        row['candidate'],
        (row['iteration'], row['electronic_activation']),
        xytext=(0, 9), textcoords='offset points',
        ha='center', fontsize=8, rotation=18,
    )

ax.set_xlim(0.5, max(df['iteration']) + 0.5)
ax.set_ylim(ylo, yhi)
ax.set_xticks(df['iteration'])
ax.set_xlabel('Evaluation number')
ax.set_ylabel('electronic_activation objective (maximize)')
ax.set_title('Electronic activation among feasible candidates\nHard-penalized infeasible points shown as red rug marks only')
ax.grid(alpha=0.3)
ax.legend(loc='best')
fig.tight_layout()

out_png = base / 'electronic_activation_feasible_only_curve.png'
fig.savefig(out_png, dpi=180)
plt.close(fig)

print(f'Wrote {out_png}')
print(f'Wrote {out_csv}')
print(feas[['iteration','candidate','phase','electronic_activation']].to_string(index=False))
