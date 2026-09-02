from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def green_score(candidate: dict) -> float:
    cat = (float(candidate["catalyst_equiv"]) - 0.001) / (0.004 - 0.001)
    tfaa = (float(candidate["TFAA_equiv"]) - 0.9) / (3.5 - 0.9)
    oxidant = (float(candidate["oxidant_equiv"]) - 0.9) / (3.0 - 0.9)
    photonic = (float(candidate["light_intensity"]) / 100.0) * ((float(candidate["residence_time_min"]) - 2.0) / (90.0 - 2.0))
    penalty = 0.25 * cat + 0.25 * tfaa + 0.25 * oxidant + 0.25 * photonic
    return max(0.0, min(100.0, 100.0 * (1.0 - penalty)))


def extract_yield_percent(result: object) -> float:
    value = _find_yield(result)
    if value is None:
        raise ValueError("RoboFlex result did not contain a numeric yield field")
    y = float(value)
    if not math.isfinite(y):
        raise ValueError(f"non-finite yield: {y}")
    return max(0.0, min(100.0, y))


def _find_yield(obj: object) -> float | None:
    if isinstance(obj, Mapping):
        for key, val in obj.items():
            if "yield" in str(key).lower() and isinstance(val, int | float):
                return float(val)
        for val in obj.values():
            found = _find_yield(val)
            if found is not None:
                return found
    elif isinstance(obj, Sequence) and not isinstance(obj, str | bytes):
        for val in obj:
            found = _find_yield(val)
            if found is not None:
                return found
    return None


def objective_values(candidate: dict, yield_percent: float) -> dict[str, float]:
    return {"yield_percent": float(yield_percent), "green_score": green_score(candidate)}
