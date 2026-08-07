"""Campaign intake construction for direct arylation BO campaign."""

from direct_arylation_bo.search_space import get_objective_definition, get_parameter_definitions


CAMPAIGN_NAME = "direct-arylation-yield-optimization-akg-eval-1dc66667d24647198d7428279470bb36"
CAMPAIGN_DESCRIPTION = (
    "Bayesian optimization of direct arylation reaction yield "
    "using a remote oracle. Campaign marker: akg-eval-1dc66667d24647198d7428279470bb36"
)


def build_intake() -> dict:
    """Construct the BO-MCP campaign intake payload."""
    return {
        "name": CAMPAIGN_NAME,
        "description": CAMPAIGN_DESCRIPTION,
        "parameters": get_parameter_definitions(),
        "objectives": [get_objective_definition()],
        "backend": "auto",
        "batch_size": 1,
        "initial_design_size": 10,
        "acquisition_method": "auto",
        "random_seed": 42,
    }


def validate_intake(intake: dict) -> dict:
    """Validate intake structure (called before creation)."""
    required_keys = {"name", "parameters", "objectives"}
    missing = required_keys - set(intake.keys())
    if missing:
        raise ValueError(f"Intake missing required keys: {missing}")
    if not intake["parameters"]:
        raise ValueError("Intake must have at least one parameter")
    if not intake["objectives"]:
        raise ValueError("Intake must have at least one objective")
    return intake