# direct_arylation_bo/search_space.py
"""Fixed search space for the direct arylation reaction.

Cache-buster: 234c0ae1-e4bc-485b-86ef-343a06547aab
"""

from __future__ import annotations

# ── parameter definitions ──────────────────────────────────────────

BASES: list[str] = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGANDS: list[str] = [
    "BrettPhos",
    "Di-tert-butylphenylphosphine",
    "(t-Bu)PhCPhos",
    "Tricyclohexylphosphine",
    "PPh3",
    "XPhos",
    "P(2-furyl)3",
    "Methyldiphenylphosphine",
    "1268824-69-6",
    "JackiePhos",
    "SCHEMBL15068049",
    "Me2PPh",
]

SOLVENTS: list[str] = [
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATIONS: list[float] = [0.057, 0.1, 0.153]

TEMPERATURES_C: list[float] = [90.0, 105.0, 120.0]

# ── parameter names (lowercase, as required) ────────────────────────

PARAM_NAMES: list[str] = [
    "base",
    "ligand",
    "solvent",
    "concentration",
    "temperature_c",
]

# ── total search space size ─────────────────────────────────────────

SPACE_SIZE: int = (
    len(BASES)
    * len(LIGANDS)
    * len(SOLVENTS)
    * len(CONCENTRATIONS)
    * len(TEMPERATURES_C)
)
# 4 * 12 * 4 * 3 * 3 = 1728