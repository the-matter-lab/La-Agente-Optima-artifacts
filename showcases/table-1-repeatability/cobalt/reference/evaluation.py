"""Read the three electronic scoring inputs for the cobalt methyl doublet."""
from pyscf.scf import chkfile, uhf


def parse_electronic_descriptors(path: str) -> dict:
    mol, scf = chkfile.load_scf(path)
    alpha_occ, beta_occ = scf["mo_occ"]
    occupied_alpha = (alpha_occ > 0.1).nonzero()[0]
    if len(occupied_alpha) != (beta_occ > 0.1).sum() + 1:
        raise ValueError("Expected the alpha-majority doublet for the methyl complex")
    somo = scf["mo_energy"][0, occupied_alpha[-1]]

    co_index, = (i for i in range(mol.natm) if mol.atom_symbol(i) == "Co")
    density = uhf.make_rdm1(scf["mo_coeff"], scf["mo_occ"])
    overlap = mol.intor_symmetric("int1e_ovlp")
    populations, charges = uhf.mulliken_pop(mol, density, s=overlap, verbose=0)
    start, end = mol.aoslice_by_atom()[co_index][2:4]
    alpha = float(populations[0][start:end].sum())
    beta = float(populations[1][start:end].sum())
    return {
        "somo_energy_hartree": float(somo),
        "co_mulliken_charge": float(charges[co_index]),
        "co_mulliken_spin_population": alpha - beta,
        "provenance": "chkfile_preferred",
    }
