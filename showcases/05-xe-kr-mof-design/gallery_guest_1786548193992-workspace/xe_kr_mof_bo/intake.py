from __future__ import annotations


def build_intake(space: dict, *, name: str, batch_size: int = 3, total_budget: int = 30, initial_design_size: int = 9) -> dict:
    return {
        "name": name,
        "description": (
            "BayBE campaign over PORMAKE topology + node building block + edge building block. "
            "External evaluator constructs MOFs with PORMAKE and scores Zeo++ pore metrics for Xe/Kr separation."
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "max_iterations": max(1, total_budget // batch_size),
        "max_observations": total_budget,
        "scalarization": "desirability",
        "scalarizer": "geom_mean",
        "parameters": [
            {"name": "topology", "type": "categorical", "categories": space["topologies"]},
            {"name": "node", "type": "categorical", "categories": space["nodes"]},
            {"name": "edge", "type": "categorical", "categories": space["edges"]},
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
