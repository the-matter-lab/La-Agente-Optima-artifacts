from __future__ import annotations

from copy import deepcopy
from typing import Final

CAMPAIGN_SLUG: Final[str] = "ethanol_sds_contact_angle_65"
TARGET_ANGLE_DEG: Final[float] = 65.0
MATCH_TOLERANCE_DEG: Final[float] = 1.0
ETHANOL_BOUNDS: Final[tuple[float, float]] = (0.0, 50.0)
SDS_BOUNDS: Final[tuple[float, float]] = (0.0, 1.0)

PARAMETERS: Final[list[dict[str, object]]] = [
    {
        "name": "Ethanol",
        "type": "continuous",
        "bounds": {"lower": ETHANOL_BOUNDS[0], "upper": ETHANOL_BOUNDS[1]},
        "description": "Ethanol concentration in v/v%; capped at 50 for two-reagent feasibility.",
    },
    {
        "name": "SDS",
        "type": "continuous",
        "bounds": {"lower": SDS_BOUNDS[0], "upper": SDS_BOUNDS[1]},
        "description": "SDS concentration in w/v%.",
    },
]


def build_parameters() -> list[dict[str, object]]:
    return deepcopy(PARAMETERS)
