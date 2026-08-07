"""Search-space definition: 6 continuous parameters x_1..x_6 in [0, 1]."""

from __future__ import annotations


def build_parameters() -> list[dict[str, object]]:
    """Return the list of ``InputParameter`` dicts for the Ackley-6D space."""
    return [
        {
            "name": f"x_{i}",
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
        }
        for i in range(1, 7)
    ]