from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from rdkit import Chem, rdBase
from rdkit.Chem import AllChem

ROOT = Path(__file__).resolve().parent
SMILES = {"seed": "CC1=CC2=CC=CC3=CC=CC(=C1)N32",
          "bo": "CS(=O)C1=CC=C2C=CC=C3C=CC=C1N32"}
JOBS = [(mol, i, 84000 + i * 11 + offset)
        for i in (1, 2, 3) for offset, mol in enumerate(("seed", "bo"))]

def calculate(job):
    mol_id, rep, seed = job
    folder = ROOT / f"{mol_id}-{rep}"
    folder.mkdir(exist_ok=False)
    t = time.monotonic()
    mol = Chem.AddHs(Chem.MolFromSmiles(SMILES[mol_id]))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise RuntimeError(f"Embedding failed for {job}")
    uff_status = AllChem.UFFOptimizeMolecule(mol)
    coords = ["%s %.9f %.9f %.9f" % (a.GetSymbol(), *p)
              for a,p in zip(mol.GetAtoms(), mol.GetConformer().GetPositions())]
    (folder/"crest_mol.xyz").write_text("\n".join([str(len(coords)),"0 1",*coords])+"\n")
    (folder/"crest.toml").write_text("input='crest_mol.xyz'\nruntype='imtd-gc'\nthreads=4\n[calculation]\n[[calculation.level]]\nmethod='gfn2'\ncharge=0\nuhf=0\n[cregen]\n[[calculation.constraints]]\n[dynamics]\n[[dynamics.meta]]\n")
    env = dict(os.environ, OMP_NUM_THREADS="4", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    print("start", folder.name, flush=True)
    with (folder/"crest.out").open("w") as output, (folder/"crest.err").open("w") as err:
        subprocess.run(["crest", "--input", "crest.toml", "--quick"], cwd=folder, env=env, stdout=output, stderr=err, check=True)
    if "CREST terminated normally" not in (folder/"crest.out").read_text():
        raise RuntimeError(f"Abnormal CREST termination in {folder.name}")
    lines = (folder/"crest_conformers.xyz").read_text().splitlines()
    energies, frames = [], []
    i=0
    while i<len(lines):
        if not lines[i].strip():
            i += 1
            continue
        n = int(lines[i])
        frame = lines[i:i+n+2]
        assert n == len(coords) and len(frame) == n+2
        energies.append(float(frame[1].split()[0]))
        frames.append(frame)
        i += n+2
    assert energies[0] <= min(energies) + 1e-8
    (folder/"selected.xyz").write_text("\n".join(frames[0])+"\n")
    data=dict(molecule=mol_id,repeat=rep,smiles=SMILES[mol_id],rdkit=rdBase.rdkitVersion,rdkit_seed=seed,uff_status=uff_status,crest_s=time.monotonic()-t,n_conformers=len(frames),energies_hartree=energies,selected_index=0,initial_sha256=hashlib.sha256((folder/"crest_mol.xyz").read_bytes()).hexdigest(),selected_sha256=hashlib.sha256((folder/"selected.xyz").read_bytes()).hexdigest())
    tmp=folder/"conformer.tmp"
    tmp.write_text(json.dumps(data,indent=2)+"\n")
    tmp.rename(folder/"conformer.json")
    print("complete",folder.name,len(frames),flush=True)

if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(calculate,JOBS))
