"""Search space construction for Ackley 6D optimization."""

from domains.bo_mcp.client import BoMcpClient


def build_parameters() -> list[dict]:
    """Build the 6 continuous parameters x_1 through x_6 in [0, 1]."""
    parameters = []
    for i in range(1, 7):
        parameters.append(
            {
                "name": f"x_{i}",
                "type": "continuous",
                "bounds": {"lower": 0.0, "upper": 1.0},
                "description": f"Normalized coordinate {i} for Ackley function",
            }
        )
    return parameters


def build_objectives() -> list[dict]:
    """Build the surface_response objective (maximize)."""
    return [
        {
            "name": "surface_response",
            "target_mode": "maximize",
            "unit": "normalized_unitless",
            "weight": 1.0,
        }
    ]


def build_intake(
    *,
    name: str,
    random_seed: int = 42,
    initial_design_size: int = 10,
    batch_size: int = 1,
    max_observations: int = 60,
    backend: str = "auto",
    acquisition_method: str = "auto",
) -> dict:
    """Build the complete campaign intake payload.

    Args:
        name: Campaign name (must contain ownership marker).
        random_seed: RNG seed for reproducibility.
        initial_design_size: Number of Sobol initial points.
        batch_size: Suggestions per generation call.
        max_observations: Hard cap on total evaluations.
        backend: "auto" | "botorch" | "baybe".
        acquisition_method: Acquisition function (e.g., "noisy_ei", "upper_confidence_bound", "auto").

    Returns:
        Intake dict ready for BoMcpClient.validate_intake / create_campaign.
    """
    return {
        "name": name,
        "description": "Ackley 6D synthetic benchmark - maximize surface_response",
        "parameters": build_parameters(),
        "objectives": build_objectives(),
        "backend": backend,
        "acquisition_method": acquisition_method,
        "random_seed": random_seed,
        "initial_design_size": initial_design_size,
        "batch_size": batch_size,
        "max_observations": max_observations,
        # Do not set max_iterations - leave unset per policy (CLI budgets bound invocations)
    }


def validate_intake(client: BoMcpClient, intake: dict) -> dict:
    """Validate intake against BO-MCP API."""
    return client.validate_intake(intake)