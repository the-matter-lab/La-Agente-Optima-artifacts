from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import Descriptors, rdFingerprintGenerator
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class Candidate:
    molecule_key: str
    smiles_canonical: str
    heavy_atoms: int
    descriptors: dict[str, float]


SCALAR_DESCRIPTOR_NAMES = [
    "mol_wt",
    "exact_mol_wt",
    "heavy_atoms",
    "hetero_atoms",
    "hbd",
    "hba",
    "tpsa",
    "logp",
    "rotatable_bonds",
    "ring_count",
    "aromatic_rings",
    "fraction_csp3",
]


def _mol_from_smiles(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"RDKit could not parse SMILES: {smiles}")
    return mol


def _scalar_descriptors(mol: Chem.Mol) -> list[float]:
    return [
        float(Descriptors.MolWt(mol)),
        float(Descriptors.ExactMolWt(mol)),
        float(mol.GetNumHeavyAtoms()),
        float(Descriptors.NumHeteroatoms(mol)),
        float(Descriptors.NumHDonors(mol)),
        float(Descriptors.NumHAcceptors(mol)),
        float(Descriptors.TPSA(mol)),
        float(Descriptors.MolLogP(mol)),
        float(Descriptors.NumRotatableBonds(mol)),
        float(Descriptors.RingCount(mol)),
        float(Descriptors.NumAromaticRings(mol)),
        float(Descriptors.FractionCSP3(mol)),
    ]


def _fingerprint_array(mol: Chem.Mol, generator) -> np.ndarray:
    fp = generator.GetFingerprint(mol)
    arr = np.zeros((fp.GetNumBits(),), dtype=float)
    DataStructs.ConvertToNumpyArray(fp, arr)
    return arr


def load_candidates(
    csv_path: str,
    heavy_atom_cutoff: int = 56,
    limit: int | None = None,
    fingerprint_components: int = 32,
    random_seed: int = 2021,
) -> list[Candidate]:
    df = pd.read_csv(csv_path)
    required = {"molecule_key", "smiles_canonical"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    rows: list[tuple[str, str, Chem.Mol, int, list[float], np.ndarray]] = []
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    for row in df.itertuples(index=False):
        key = str(getattr(row, "molecule_key"))
        smiles = str(getattr(row, "smiles_canonical"))
        mol = _mol_from_smiles(smiles)
        heavy_atoms = int(mol.GetNumHeavyAtoms())
        if heavy_atoms >= heavy_atom_cutoff:
            continue
        rows.append((key, smiles, mol, heavy_atoms, _scalar_descriptors(mol), _fingerprint_array(mol, generator)))

    if limit is not None:
        rows = rows[:limit]
    if len(rows) < 2:
        raise ValueError("At least two candidates are required for a categorical BO campaign.")

    scalars = np.asarray([r[4] for r in rows], dtype=float)
    fps = np.asarray([r[5] for r in rows], dtype=float)
    n_components = min(fingerprint_components, max(1, len(rows) - 1), fps.shape[1] - 1)
    fp_features = TruncatedSVD(n_components=n_components, random_state=random_seed).fit_transform(fps)
    features = np.hstack([scalars, fp_features])
    features = StandardScaler().fit_transform(features)

    names = SCALAR_DESCRIPTOR_NAMES + [f"ecfp4_svd_{i:02d}" for i in range(n_components)]
    variances = np.var(features, axis=0)
    keep = variances > 1e-12
    features = features[:, keep]
    names = [name for name, flag in zip(names, keep) if flag]

    identity = np.linspace(0.0, 1.0, num=len(rows), dtype=float).reshape(-1, 1)
    features = np.hstack([features, identity])
    names.append("identity_code")

    candidates: list[Candidate] = []
    for i, (key, smiles, _mol, heavy_atoms, _scalars, _fp) in enumerate(rows):
        descriptors = {name: float(features[i, j]) for j, name in enumerate(names)}
        candidates.append(Candidate(key, smiles, heavy_atoms, descriptors))
    return candidates


def as_lookup(candidates: list[Candidate]) -> dict[str, Candidate]:
    return {candidate.molecule_key: candidate for candidate in candidates}
