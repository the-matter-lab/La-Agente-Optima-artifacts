"""Campaign intake construction for direct arylation BO-MCP campaign."""

from __future__ import annotations

from direct_arylation_campaign.search_space import get_objective_definition, get_parameter_definitions


MARKER = "akg-eval-0c360b08e6684de0b0ed04f50bde3b2c"
NONCE = "16e7e684-7bf5-4a9b-af93-fae14403be06"


def build_intake() -> dict:
    """Build the campaign intake payload for BO-MCP."""
    return {
        "name": f"direct_arylation_yield_opt_{MARKER}_{NONCE}",
        "description": (
            "Bayesian optimization of direct arylation reaction yield over "
            "a fixed fully crossed search space of 1,728 measured reactions. "
            "Budget: 60 oracle evaluations. Marker: {MARKER}. Nonce: {NONCE}."
        ),
        "parameters": get_parameter_definitions(),
        "objectives": [get_objective_definition()],
        "backend": "auto",
        "acquisition_method": "auto",
        "batch_size": 1,
        "initial_design_size": 10,  # Sobol/LHS warmup before model-driven BO
        "max_observations": 60,  # Hard budget cap on total evaluations
        "random_seed": 42,  # Reproducible initial design
    }


def validate_intake(intake: dict) -> None:
    """Validate intake structure has required fields."""
    required = {"name", "parameters", "objectives"}
    missing = required - set(intake.keys())
    if missing:
        raise ValueError(f"Intake missing required fields: {missing}")
    if not intake["parameters"]:
        raise ValueError("Intake must have at least one parameter")
    if not intake["objectives"]:
        raise ValueError("Intake must have at least one objective")
    obj = intake["objectives"][0]
    if obj.get("name") != "yield":
        raise ValueError("Objective name must be 'yield'")
    if obj.get("target_mode") != "maximize":
        raise ValueError("Objective direction must be maximize")