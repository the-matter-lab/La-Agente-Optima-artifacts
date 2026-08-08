# direct_arylation/intake.py

from .search_space import get_parameters

def create_campaign_intake(campaign_name: str | None = None) -> dict:
    """Create the campaign intake payload.
    
    The campaign name must include the exact marker:
    akg-eval-3032662cf5a04c1a98983c411654768c
    """
    marker = "akg-eval-3032662cf5a04c1a98983c411654768c"
    if campaign_name:
        if marker not in campaign_name:
            name = f"{campaign_name}_{marker}"
        else:
            name = campaign_name
    else:
        name = f"direct_arylation_optimization_{marker}"
        
    return {
        "name": name,
        "description": "Direct arylation reaction-yield optimization benchmark",
        "backend": "auto",
        "objectives": [
            {
                "name": "yield",
                "direction": "maximize"
            }
        ],
        "parameters": get_parameters()
    }
