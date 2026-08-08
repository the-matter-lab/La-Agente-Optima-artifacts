"""Campaign intake payload for the 6-D Ackley benchmark."""

import uuid

OWNERSHIP_MARKER = "akg-eval-8c5ca00fb69c4b67af14d0be90fef5f8"


def build_intake() -> dict:
    """Return the campaign intake dict for BO-MCP."""
    return {
        "name": f"ackley-6d-{OWNERSHIP_MARKER}",
        "description": "Synthetic Ackley surface optimization in 6 normalized dimensions.",
        "backend": "baybe",
        "random_seed": 42,
        "initial_design_size": 12,
        "batch_size": 3,
"acquisition_method": "expected_improvement",
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            },
        ],
        "parameters": [
            {"name": f"x_{i}", "type": "continuous", "bounds": {"lower": 0.0, "upper": 1.0}}
            for i in range(1, 7)
        ],
    }


def make_idempotency_key(prefix: str) -> str:
    """Generate a stable idempotency key with a random suffix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"