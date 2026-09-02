#!/usr/bin/env python3
import json, itertools
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base=Path(__file__).resolve().parent
records=[]
for line in (base/'evaluations.jsonl').read_text().splitlines():
    if not line.strip():
        continue
    r=json.loads(line)
    cand=(r.get('candidate') or {}).get('candidate_id') or r.get('candidate_id')
    obj=r.get('objectives') or {}
    rec={'candidate':cand,'phase':r.get('phase'),'feasible':bool(r.get('feasible')),
         'electronic':float(obj.get('electronic_activation')),
         'stability':float(obj.get('coordination_stability')),
         'geometry':float(obj.get('chelate_geometry')),
         'steric':float(obj.get('steric_crowding'))}
    records.append(rec)
feas=[r for r in records if r['feasible']]
if not feas:
    raise SystemExit('No feasible records yet')
Y=np.array([[r['electronic'],r['stability'],r['geometry'],-r['steric']] for r in feas],float)
ref=Y.min(axis=0)-1.0

def pareto(points):
    keep=np.ones(len(points),bool)
    for i in range(len(points)):
        if np.any(np.all(points>=points[i],axis=1)&np.any(points>points[i],axis=1)):
            keep[i]=False
    return keep

def hv(points):
    pts=np.array(points,float)
    pts=pts[np.all(pts>ref,axis=1)]
    pts=pts[pareto(pts)]
    total=0.0
    for k in range(1,len(pts)+1):
        sign=1 if k%2 else -1
        for combo in itertools.combinations(range(len(pts)),k):
            upper=np.min(pts[list(combo)],axis=0)
            total += sign*float(np.prod(np.maximum(upper-ref,0)))
    return max(total,0.0)

hvs=[hv(Y[:i]) for i in range(1,len(Y)+1)]
norm=np.array(hvs)/(hvs[-1] if hvs[-1] else 1.0)
for i,r in enumerate(feas):
    r['feasible_index']=i+1; r['hypervolume']=hvs[i]; r['norm_hv']=float(norm[i]); r['pareto']=bool(pareto(Y[:i+1])[-1])

fig,ax=plt.subplots(figsize=(8,4.8))
x=np.arange(1,len(feas)+1)
ax.plot(x,norm,marker='o',lw=2.2,color='#1f77b4')
for xi,r in zip(x,feas):
    ax.annotate(r['candidate'],(xi,r['norm_hv']),textcoords='offset points',xytext=(0,8),ha='center',fontsize=8,rotation=15)
ax.set_ylim(0,1.08)
ax.set_xticks(x)
ax.set_xlabel('Feasible evaluation number')
ax.set_ylabel('Normalized feasible-only hypervolume')
ax.set_title('Feasible-only BO improvement so far\nPBE/def2-SVP strict-convergence campaign')
ax.grid(alpha=.3)
fig.tight_layout()
out=base/'feasible_improvement_so_far.png'
fig.savefig(out,dpi=180)
# write summary
import csv
csvout=base/'feasible_improvement_so_far.csv'
with csvout.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(feas[0].keys()))
    w.writeheader(); w.writerows(feas)
print(out)
print(csvout)
print('feasible',len(feas),'of',len(records),'normalized_hv',norm.tolist())
