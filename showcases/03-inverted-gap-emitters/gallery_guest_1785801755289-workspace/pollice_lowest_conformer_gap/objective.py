from __future__ import annotations

import math
from typing import Any

from domains.pyscf.tools.conversion_tools import UnitConvPair, get_conversion_factor

EV_PER_HARTREE = float(get_conversion_factor([UnitConvPair(value=1.0, from_unit="hartree", to_unit="eV")])[0])


def as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": value}


def _flatten_numbers(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return [float(value)]
    if isinstance(value, dict):
        out: list[float] = []
        for item in value.values():
            out.extend(_flatten_numbers(item))
        return out
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            out.extend(_flatten_numbers(item))
        return out
    return []


def _find_values(tddft: dict[str, Any], token: str) -> tuple[str, list[float]]:
    preferred = [
        key for key in tddft
        if token in key.lower() and "energ" in key.lower() and _flatten_numbers(tddft[key])
    ]
    if preferred:
        key = sorted(preferred, key=len)[0]
        return key, _flatten_numbers(tddft[key])
    for key, value in tddft.items():
        if token in key.lower():
            values = _flatten_numbers(value)
            if values:
                return key, values
    return "", []


def _energy_to_ev(value: float, source_key: str) -> float:
    key = source_key.lower()
    if "ev" in key:
        return float(value)
    if abs(value) < 1.5:
        return float(value) * EV_PER_HARTREE
    return float(value)


def extract_gap(result: Any) -> dict[str, float | None]:
    data = as_dict(result)
    tddft = data.get("tddft_results") or data.get("tddft") or {}
    if not isinstance(tddft, dict):
        raise ValueError("PySCF result did not contain a TD-DFT results mapping.")

    singlet_key, singlets = _find_values(tddft, "singlet")
    triplet_key, triplets = _find_values(tddft, "triplet")
    if not singlets:
        raise ValueError("No singlet TD-DFT energies found in PySCF result.")
    if not triplets:
        raise ValueError("No triplet TD-DFT energies found in PySCF result.")

    s1_index, s1_raw = min(enumerate(singlets), key=lambda item: item[1])
    _t1_index, t1_raw = min(enumerate(triplets), key=lambda item: item[1])
    s1_ev = _energy_to_ev(float(s1_raw), singlet_key)
    t1_ev = _energy_to_ev(float(t1_raw), triplet_key)
    delta_est_ev = s1_ev - t1_ev

    osc_key = next((key for key in tddft if "oscillator" in key.lower()), "")
    oscillator_values = _flatten_numbers(tddft.get(osc_key)) if osc_key else []
    oscillator_strength = None
    if oscillator_values and s1_index < len(oscillator_values):
        oscillator_strength = float(oscillator_values[s1_index])

    return {
        "S1_ev": float(s1_ev),
        "T1_ev": float(t1_ev),
        "delta_est_ev": float(delta_est_ev),
        "objective": float(-delta_est_ev),
        "oscillator_strength": oscillator_strength,
    }
