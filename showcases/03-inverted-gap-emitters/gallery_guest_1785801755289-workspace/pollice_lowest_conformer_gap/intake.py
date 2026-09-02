from __future__ import annotations

from .search_space import Candidate

OBJECTIVE_NAME = "negative_singlet_triplet_gap"
PARAMETER_NAME = "molecule_key"


def build_intake(
    candidates: list[Candidate],
    *,
    name: str = "Pollice 2021 lowest-conformer TD-DFT gap",
    batch_size: int = 2,
    initial_design_size: int = 5,
    random_seed: int = 2021,
) -> dict:
    categories = [candidate.molecule_key for candidate in candidates]
    descriptors = {candidate.molecule_key: candidate.descriptors for candidate in candidates}
    return {
        "name": name,
        "description": (
            "Fixed-library molecule BO over Pollice 2021 rows filtered to heavy_atoms < 56. "
            "Objective maximizes -(S1_ev - T1_ev) from CREST/GFN2 lowest conformer followed by "
            "restricted closed-shell PBE0/def2-SVP gas-phase TD-DFT."
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "random_seed": random_seed,
        "parameters": [
            {
                "name": PARAMETER_NAME,
                "type": "categorical",
                "categories": categories,
                "description": "Filtered CSV molecule_key; smiles_canonical is looked up locally for evaluation.",
                "parameter_options": {
                    "baybe": {
                        "role": "custom",
                        "custom_descriptors": descriptors,
                        "decorrelate": False,
                    }
                },
            }
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": "eV",
            }
        ],
    }
