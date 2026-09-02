from __future__ import annotations


def build_followup_intake(space: dict, *, name: str, batch_size: int = 5, new_budget: int = 50, seed_count: int = 0) -> dict:
    return {
        "name": name,
        "description": (
            "Refined follow-up BayBE campaign for PORMAKE/Zeo++ Xe/Kr MOFs. "
            "The BO parameter is a finite candidate_id that decodes exactly to topology|node|edge, "
            "so all generated choices are compatible triples learned from prior artifacts."
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "max_iterations": max(1, (new_budget + batch_size - 1) // batch_size),
        "max_observations": seed_count + new_budget,
        "scalarization": "desirability",
        "scalarizer": "geom_mean",
        "parameters": [
            {"name": "candidate_id", "type": "categorical", "categories": space["candidate_ids"]},
        ],
        "objectives": [
            {
                "name": "selectivity_proxy",
                "direction": "maximize",
                "unit": "0-1 proxy",
                "weight": 0.6,
                "normalization_bounds": [0.0, 1.0],
            },
            {
                "name": "capacity_proxy",
                "direction": "maximize",
                "unit": "cm^3/g pore volume proxy",
                "weight": 0.4,
                "normalization_bounds": [0.0, 10.0],
            },
        ],
        "random_seed": 20260812,
    }
