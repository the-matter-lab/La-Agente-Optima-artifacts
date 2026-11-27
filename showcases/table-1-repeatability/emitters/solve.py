import json
from pathlib import Path
import sys
import time

import cupy
import gpu4pyscf
import numpy
import pyscf
import qcelemental
from pyscf import dft, gto, lib
import gpu4pyscf.tdscf.rks

def array(v):
    return numpy.asarray(v.get() if hasattr(v,"get") else v)

def solve(folder):
    start = time.monotonic()
    provenance=json.loads((folder/"conformer.json").read_text())
    dev = cupy.cuda.runtime.getDeviceProperties(0)["name"].decode()
    assert cupy.cuda.runtime.getDeviceCount() == 1 and dev == "NVIDIA RTX A4000"
    lib.num_threads(2)
    xyz = (folder/"selected.xyz").read_text().splitlines()
    assert len(xyz[2:]) == int(xyz[0])
    mol = gto.M(atom="\n".join(xyz[2:]), unit="Angstrom",basis="def2-svp",
                charge=0, spin=0, verbose=4)
    cpu = dft.RKS(mol)
    cpu.xc = "PBE0"
    mf = cpu.density_fit().to_gpu()
    assert type(mf).__module__.startswith("gpu4pyscf")
    mf.chkfile = str(folder/"scf.chk")
    scf_energy=mf.kernel()
    if not mf.converged:
        raise RuntimeError("SCF did not converge")
    td = mf.TDDFT()
    td.nstates=5
    td.conv_tol=1e-6
    print("GPU", dev, type(mf), type(td), flush=True)
    eV = qcelemental.constants.conversion_factor("hartree", "eV")
    roots={}
    convergence={}
    for label, singlet in (("singlet",True),("triplet",False)):
        td.singlet=singlet
        td.kernel()
        roots[label] = (array(td.e).copy()*eV).tolist()
        convergence[label] = array(td.converged).astype(bool).tolist()
        assert len(roots[label]) == 5 and numpy.isfinite(roots[label]).all() and min(roots[label]) > 0
        if not numpy.all(convergence[label]):
            raise RuntimeError(f"{label}: unconverged roots {convergence[label]}")
    s1=min(roots["singlet"])
    t1=min(roots["triplet"])
    data=dict(**provenance,gpu=dev,gpu4pyscf=gpu4pyscf.__version__,pyscf=pyscf.__version__,cupy=cupy.__version__,grid_level=mf.grids.level,scf_converged=bool(mf.converged),scf_tol=mf.conv_tol,scf_energy_hartree=float(scf_energy),td_tol=td.conv_tol,solver=type(td).__module__+"."+type(td).__name__,converged=convergence,roots_eV=roots,S1_eV=s1,T1_eV=t1,gap_eV=s1-t1,td_run_seconds=time.monotonic()-start)
    tmp=folder/"result.tmp"
    tmp.write_text(json.dumps(data,indent=2)+"\n")
    tmp.rename(folder/"result.json")
    print("FINAL",folder.name,s1,t1,s1-t1,flush=True)

if __name__=="__main__":
    solve(Path(sys.argv[1]).resolve())
