import csv
import json
from pathlib import Path
from statistics import mean, stdev
from itertools import product
from hashlib import sha256

root=Path(__file__).resolve().parent
jobs=[json.loads((root/(m+"-"+str(i))/"result.json").read_text()) for i in (1,2,3) for m in ("seed","bo")]
cols=["molecule","repeat","rdkit_seed","n_conformers","selected_sha256","S1_eV","T1_eV","gap_eV","scf_converged","gpu","solver"]
with (root/"results.csv").open("w") as f:
    w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
    w.writeheader()
    w.writerows(jobs)
gaps={}
groups={}
for m in ("seed","bo"):
    records=[j for j in jobs if j["molecule"]==m]
    assert len({j["initial_sha256"] for j in records})==3
    for j in records:
        assert abs(j["gap_eV"] - (min(j["roots_eV"]["singlet"])-min(j["roots_eV"]["triplet"])))<1e-12
        assert j["scf_converged"] and all(all(v) for v in j["converged"].values())
        assert j["gpu"]=="NVIDIA RTX A4000" and "TDA" != j["solver"].split(".")[-1]
        assert sha256((root/f"{m}-{j['repeat']}"/"selected.xyz").read_bytes()).hexdigest()==j["selected_sha256"]
    gaps[m]=[j["gap_eV"]*1000 for j in records]
    groups[m]={"mean_meV":mean(gaps[m]),"sample_sd_meV":stdev(gaps[m]),"range_meV":[min(gaps[m]),max(gaps[m])]}
diff=[s-b for s,b in product(gaps["seed"],gaps["bo"])]
hist=(0.2267869324879579-0.2232308199591746)*1000
summary={"historical_seed_minus_bo_meV":hist,"groups":groups,"mean_seed_minus_bo_meV":mean(diff),
         "cross_comparisons":len(diff),"bo_gap_smaller_count":sum(x>0 for x in diff),"min_seed_minus_bo_meV":min(diff),"max_seed_minus_bo_meV":max(diff)}
(root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
print((root/"results.csv").read_text())
print((root/"summary.json").read_text())
