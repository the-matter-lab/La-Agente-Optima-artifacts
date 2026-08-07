# Campaign intake construction for direct arylation campaign
from direct_arylation.search_space import get_parameters

def get_objectives() -> list[dict]:
    """Return the list of objectives for the direct arylation campaign."""
    return [
        {
            "name": "yield",
            "direction": "maximize",
            "unit": "percent"
        }
    ]

def build_intake(campaign_name: str) -> dict:
    """Build the campaign intake payload."""
    return {
        "name": campaign_name,
        "objectives": get_objectives(),
        "parameters": get_parameters(),
        "backend": "auto"
    }
