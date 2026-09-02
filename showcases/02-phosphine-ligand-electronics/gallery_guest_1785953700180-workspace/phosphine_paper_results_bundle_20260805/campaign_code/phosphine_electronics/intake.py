from __future__ import annotations

from .space import categories

OBJECTIVES = [
    "donor_homo_error",
    "gap_error",
    "steric_excess",
    "heavy_atom_count",
]


def build_intake(name: str, *, batch_size: int = 2, candidate_csv=None) -> dict:
    return {
        "name": name,
        "description": (
            "Finite candidate-table MOBO over neutral monodentate phosphines P(R1)(R2)(R3). "
            "Objectives are raw transformed digital ligand descriptors: HOMO target error, gap target error, "
            "volume excess above 350 A^3, and heavy-atom count. Phosphorus charge is tracked as auxiliary."
        ),
        "backend": "auto",
        "batch_size": batch_size,
        "scalarization": "pareto",
        "acquisition_method": "hypervolume_improvement",
        "parameters": [
            {
                "name": "candidate_id",
                "type": "categorical",
                "categories": categories(candidate_csv) if candidate_csv else categories(),
                "description": "Pre-enumerated ligand row id in candidate_table.csv; no graph assembly during BO.",
            }
        ],
        "objectives": [
            {"name": "donor_homo_error", "direction": "minimize", "unit": "eV"},
            {"name": "gap_error", "direction": "minimize", "unit": "eV"},
            {"name": "steric_excess", "direction": "minimize", "unit": "angstrom^3"},
            {"name": "heavy_atom_count", "direction": "minimize", "unit": "count"},
        ],
        "random_seed": 31841,
    }
