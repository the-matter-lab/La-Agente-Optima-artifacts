"""A4000 standalone execution of the August Gráfico PBE geometry/scoring workflow."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

import cupy, gpu4pyscf, numpy as np, pyscf
from pyscf import dft, gto, lib
from pyscf.geomopt import geometric_solver
from reference.descriptors import electronic_activation_components, geometry_descriptors, objective_scores
from reference.evaluation import parse_electronic_descriptors
from xyz import parse_xyz

ROOT=Path(__file__).resolve().parent

def save(path,data):
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(data,indent=2)+"\n")
    temp.replace(path)

def write_xyz(path, symbols, coords, comment):
    text=[str(len(symbols)),comment]+[f"{sym:2s} {x: .10f} {y: .10f} {z: .10f}" for sym,(x,y,z) in zip(symbols,coords)]
    path.write_text("\n".join(text)+"\n")

def run(folder):
    os.chdir(folder)
    meta=json.loads(Path("build.json").read_text())
    cid=meta["candidate_id"]
    ref_atoms=parse_xyz(str(ROOT/"reference"/cid/(cid+".xyz")))
    atoms=parse_xyz("start.xyz")
    assert len(atoms)==len(ref_atoms) and Counter(a[0] for a in atoms)==Counter(a[0] for a in ref_atoms), "incorrect atom counts for requested complex"
    grid_dtype=np.asarray([row[1:] for row in atoms])
    assert np.isfinite(grid_dtype).all()
    gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode()
    assert gpu=="NVIDIA RTX A4000" and cupy.cuda.runtime.getDeviceCount()==1
    started=time.monotonic()
    lib.num_threads(2)
    mol=gto.Mole()
    mol.atom=[(a[0],a[1:]) for a in atoms]
    mol.unit="Angstrom"
    mol.basis="def2-svp"
    mol.charge=1
    mol.spin=1
    mol.verbose=3
    mol.build()
    assert mol.nelectron=={"eth__Et__Et":193,"eth__Me__Me":161}[cid]
    cpu=dft.UKS(mol)
    cpu.xc="PBE"
    mf=cpu.density_fit().to_gpu()
    assert type(mf).__module__.startswith("gpu4pyscf")
    mf.chkfile=str(folder/"pbe.chk")
    print("GPU",gpu,"solver",type(mf),"atoms",mol.natm,"nao",mol.nao_nr(),flush=True)
    initial_energy=float(mf.kernel())
    initial_converged=bool(mf.converged)
    print("INITIAL_SCF_CONVERGED",initial_converged,flush=True)
    outcome={"meta":meta,"candidate_id":cid,"gpu":gpu,"gpu4pyscf":gpu4pyscf.__version__,"pyscf":pyscf.__version__,
             "initial_energy_Eh":initial_energy,"initial_scf_converged":initial_converged,"initial_descriptors":geometry_descriptors(atoms)}
    symbols=[a[0] for a in atoms]
    def step(env):
        coords=np.asarray(env["coords"]).reshape(-1,3)*lib.param.BOHR
        grad=np.asarray(env["gradients"])
        row={"step":env["self"].cycle,"energy_Eh":float(env["energy"]),"grad_norm":float(np.linalg.norm(grad))}
        with Path("steps.jsonl").open("a") as f:
            f.write(json.dumps(row)+"\n")
        write_xyz(Path("latest.xyz"),symbols,coords,"step %d"%row["step"])
        print("STEP",row,flush=True)
    converged,opt=geometric_solver.kernel(mf,callback=step,maxsteps=200,
                       logIni=str(ROOT/"reference/geometric_log.ini"))
    outcome["geometry_converged"]=bool(converged)
    if not converged:
        outcome["reason"]="geometry step limit"
    # Match historical get_optimized_mol's conversion and final single point.
    opt.set_geom_(opt.atom_coords()*0.529177,unit="Angstrom")
    mf.mol=opt
    final_energy=float(mf.kernel())
    coords=opt.atom_coords(unit="Angstrom")
    atoms=[(a,*xyz) for a,xyz in zip(symbols,coords)]
    write_xyz(Path("optimized.xyz"),symbols,coords,f"{cid} PBE/def2-SVP")
    geom=geometry_descriptors(atoms)
    el=parse_electronic_descriptors("pbe.chk")
    validity={"scf_converged":bool(mf.converged),"optimization_success":bool(converged)}
    scores=objective_scores(validity,geom,el)
    # The historical workflow label uses normal return from optimize() and
    # presence of an energy as its completion signal. Save both tests.
    archived_scores=objective_scores({"scf_converged":True,"optimization_success":True},geom,el)
    outcome["archived_return_rule_objectives"]=archived_scores
    outcome["archived_return_rule_feasible"]=archived_scores["steric_crowding"]<99
    outcome.update(final_scf_converged=bool(mf.converged),final_energy_Eh=final_energy,geom=geom,
                   electronic=el,activation_components=electronic_activation_components(el),
                   objectives=scores,feasible=all(v>-99 for k,v in scores.items() if k!="steric_crowding") and scores["steric_crowding"]<99,
                   steps=len(Path("steps.jsonl").read_text().splitlines()),seconds=time.monotonic()-started)
    save(Path("result.json"),outcome)
    print("FINISHED",cid,outcome["feasible"],scores,flush=True)
if __name__=="__main__":
    run(Path(sys.argv[1]).resolve())
