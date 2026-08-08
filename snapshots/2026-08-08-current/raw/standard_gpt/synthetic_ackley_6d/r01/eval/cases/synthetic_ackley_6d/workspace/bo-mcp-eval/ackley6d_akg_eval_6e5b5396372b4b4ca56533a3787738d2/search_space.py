from __future__ import annotations

import json
from typing import Any

CACHE_BUSTER_NONCE = "7b86fd35-b943-4816-b7ba-82e865684bf2"
CAMPAIGN_MARKER = "akg-eval-6e5b5396372b4b4ca56533a3787738d2"
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_UNIT = "normalized_unitless / normalized unitless response"
DIMENSIONS = 6
TOTAL_BUDGET = 60
LOWER_BOUND = 0.0
UPPER_BOUND = 1.0
RAW_RESPONSE_MIN = -22.350402387287602
PARAMETER_NAMES = tuple(f"x_{index}" for index in range(1, DIMENSIONS + 1))


def build_parameters() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": LOWER_BOUND, "upper": UPPER_BOUND},
            "description": "Normalized Ackley coordinate.",
        }
        for name in PARAMETER_NAMES
    ]


def normalize_parameter_values(parameter_values: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for name in PARAMETER_NAMES:
        if name not in parameter_values:
            raise KeyError(f"Missing parameter {name}")
        value = float(parameter_values[name])
        if not LOWER_BOUND <= value <= UPPER_BOUND:
            raise ValueError(f"Parameter {name}={value} is outside [{LOWER_BOUND}, {UPPER_BOUND}]")
        normalized[name] = value
    return normalized


def parameter_key(parameter_values: dict[str, Any]) -> str:
    normalized = normalize_parameter_values(parameter_values)
    payload = {name: format(normalized[name], ".17g") for name in PARAMETER_NAMES}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_campaign_name(label: str) -> str:
    cleaned = "-".join(label.strip().split()) or "main"
    return f"ackley6d-{cleaned}-{CAMPAIGN_MARKER}"
