"""Campaign intake construction for 6D Ackley optimization.

This module builds the IntakeData payload for BO-MCP campaign creation.
The campaign name includes the required marker: akg-eval-aadeb62aa2334f789ebf84ff0f1e2a45
Cache-buster nonce: 87fe1294-416b-4ab4-8491-0d8cb2c43c23
"""

from typing import Any
from pydantic import BaseModel, Field


class Bounds(BaseModel):
    lower: float
    upper: float


class InputParameter(BaseModel):
    name: str
    type: str  # "continuous"
    bounds: Bounds
    description: str = ""


class Objective(BaseModel):
    name: str
    direction: str  # "maximize"
    unit: str = "normalized_unitless"
    target_mode: str | None = None


class IntakeData(BaseModel):
    name: str
    objectives: list[Objective]
    parameters: list[InputParameter]
    batch_size: int = 1
    initial_design_size: int | None = None
    max_observations: int | None = None
    random_seed: int | None = None
    backend: str = "auto"
    acquisition_method: str = "auto"
    acknowledge_degradations: list[str] = Field(default_factory=list)


MARKER = "akg-eval-aadeb62aa2334f789ebf84ff0f1e2a45"
CACHE_BUSTER = "87fe1294-416b-4ab4-8491-0d8cb2c43c23"
CAMPAIGN_NAME = f"ackley_6d_{MARKER}_{CACHE_BUSTER}"


def build_intake(
    *,
    batch_size: int = 1,
    initial_design_size: int | None = 12,
    max_observations: int = 60,
    random_seed: int | None = 42,
) -> IntakeData:
    """Build the campaign intake for 6D Ackley optimization."""
    parameters = [
        InputParameter(
            name=f"x_{i}",
            type="continuous",
            bounds=Bounds(lower=0.0, upper=1.0),
            description=f"Input parameter x_{i} in [0, 1]",
        )
        for i in range(1, 7)
    ]

    objectives = [
        Objective(
            name="surface_response",
            direction="maximize",
            unit="normalized_unitless",
        )
    ]

    return IntakeData(
        name=CAMPAIGN_NAME,
        objectives=objectives,
        parameters=parameters,
        batch_size=batch_size,
        initial_design_size=initial_design_size,
        max_observations=max_observations,
        random_seed=random_seed,
        backend="auto",
        acquisition_method="auto",
        acknowledge_degradations=[],
    )


def intake_to_dict(intake: IntakeData) -> dict[str, Any]:
    """Convert IntakeData to dict for JSON serialization."""
    return intake.model_dump(mode="json", exclude_none=True)