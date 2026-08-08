"""Search-space definitions for the direct-arylation yield-optimisation campaign.

All five parameters are categorical (even the numeric-looking ones are
discrete values from a fixed set).
"""

from __future__ import annotations

# ── parameter value sets (exact lowercase names as specified) ──────────
BASES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]

LIGANDS = [
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

SOLVENTS = [
    "DMAc",
    "Butyornitrile",
    "Butyl Ester",
    "p-Xylene",
]

CONCENTRATIONS = [0.057, 0.1, 0.153]

TEMPERATURES_C = [90, 105, 120]

# ── parameter definitions for BO-MCP intake ────────────────────────────

PARAMETERS = [
    {
        "name": "base",
        "type": "categorical",
        "categories": BASES,
    },
    {
        "name": "ligand",
        "type": "categorical",
        "categories": LIGANDS,
    },
    {
        "name": "solvent",
        "type": "categorical",
        "categories": SOLVENTS,
    },
    {
        "name": "concentration",
        "type": "categorical",
        "categories": [str(c) for c in CONCENTRATIONS],
    },
    {
        "name": "temperature_c",
        "type": "categorical",
        "categories": [str(t) for t in TEMPERATURES_C],
    },
]

# Total search-space size: 4 × 12 × 4 × 3 × 3 = 1 728
SPACE_SIZE = len(BASES) * len(LIGANDS) * len(SOLVENTS) * len(CONCENTRATIONS) * len(TEMPERATURES_C)