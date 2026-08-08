"""BO-MCP campaign intake construction (BayBE backend, single objective).

Ownership marker (must appear in every BO-MCP campaign created by this
invocation): akg-eval-9209d1682dba47dfb5f5735d25356061
Cache-buster nonce (preserved verbatim): 4b764ac7-d36a-4203-89a4-800a2274f65c
"""
from .search_space import build_parameters

MARKER = "akg-eval-9209d1682dba47dfb5f5735d25356061"
CAMPAIGN_NAME = f"direct-arylation-yield-baybe-{MARKER}"
OBJECTIVE_NAME = "yield"


def build_intake(*, batch_size: int, initial_design_size: int) -> dict:
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            "Direct arylation reaction-yield optimization over a fixed, fully "
            "crossed 1728-candidate search space; every measurement comes "
            "from the DIRECT_ARYLATION_API_URL oracle. "
            "Nonce: 4b764ac7-d36a-4203-89a4-800a2274f65c. Marker: " + MARKER
        ),
        "backend": "baybe",
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "parameters": build_parameters(),
        "objectives": [
            {"name": OBJECTIVE_NAME, "direction": "maximize", "unit": "percent"},
        ],
    }
