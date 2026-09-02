from __future__ import annotations

from .library import baybe_custom_descriptors, build_library

OBJECTIVES = (
    ("electronic_activation", "maximize", "higher SOMO/HOMO, lower positive Co charge, appropriate Co spin density"),
    ("coordination_stability", "maximize", "successful optimization and chemically reasonable Co-P/Co-O binding"),
    ("chelate_geometry", "maximize", "reasonable P-Co-P bite angle and limited square-planar distortion"),
    ("steric_crowding", "minimize", "heavy-atom crowding near Co and ligand strain"),
)


def build_intake(name: str, random_seed: int | None = None, batch_size: int = 1) -> dict:
    categories = [c.candidate_id for c in build_library()]
    return {
        "name": name,
        "description": (
            "Finite-library multi-objective BayBE campaign inspired by Hood et al., Science 2020: "
            "cationic Co(II) [Co(acac)(P2)]+ bisphosphine precursor-like complexes. "
            "Evaluations use Estructural structure generation and modest PySCF DFT geometry optimization only."
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "random_seed": random_seed,
        "scalarization": "pareto",
        "parameters": [
            {
                "name": "candidate_id",
                "type": "categorical",
                "categories": categories,
                "description": "Finite unordered linker/R1/R2 ligand candidate identifier.",
                "parameter_options": {
                    "baybe": {
                        "role": "custom",
                        "custom_descriptors": baybe_custom_descriptors(),
                        "decorrelate": False,
                    }
                },
            }
        ],
        "objectives": [
            {"name": name, "direction": direction, "unit": "score"}
            for name, direction, _ in OBJECTIVES
        ],
    }
