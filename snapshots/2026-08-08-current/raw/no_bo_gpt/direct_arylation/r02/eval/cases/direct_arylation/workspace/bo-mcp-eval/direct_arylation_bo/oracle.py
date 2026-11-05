from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests

from .search_space import BASE_INDEX, CONCENTRATION_INDEX, LIGAND_INDEX, SOLVENT_INDEX, TEMPERATURE_INDEX


@dataclass
class DirectArylationOracle:
    base_url: str
    timeout_s: float = 20.0

    def evaluate(self, candidate: Dict[str, object]) -> Tuple[str, Optional[float], Optional[str]]:
        payload = {
            "base": str(candidate["base"]),
            "ligand": str(candidate["ligand"]),
            "solvent": str(candidate["solvent"]),
            "concentration": float(candidate["concentration"]),
            "temperature_c": int(candidate["temperature_c"]),
        }
        url = self.base_url.rstrip("/") + "/v1/evaluate"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_s)
        except Exception as exc:  # noqa: BLE001
            return "failed", None, f"request_exception: {type(exc).__name__}: {exc}"
        if not response.ok:
            body = response.text.strip().replace("\n", " ")
            return "failed", None, f"http_{response.status_code}: {body[:300]}"
        try:
            data = response.json()
            value = float(data["yield"])
        except Exception as exc:  # noqa: BLE001
            return "failed", None, f"invalid_json: {type(exc).__name__}: {exc}"
        return "completed", value, None


class MockOracle:
    """Non-objective preflight oracle with structured, deterministic outputs."""

    def evaluate(self, candidate: Dict[str, object]) -> Tuple[str, Optional[float], Optional[str]]:
        b = BASE_INDEX[str(candidate["base"])]
        l = LIGAND_INDEX[str(candidate["ligand"])]
        s = SOLVENT_INDEX[str(candidate["solvent"])]
        c = CONCENTRATION_INDEX[float(candidate["concentration"])]
        t = TEMPERATURE_INDEX[int(candidate["temperature_c"])]
        token = f"{b}|{l}|{s}|{c}|{t}".encode()
        hashed = int(hashlib.sha256(token).hexdigest()[:8], 16) / 0xFFFFFFFF
        score = 25.0 + 8.0 * b + 3.7 * l + 4.5 * s + 6.0 * c + 7.0 * t
        score += 12.0 * ((l in {1, 5, 9}) and (t == 2))
        score += 9.5 * ((b in {1, 3}) and (s in {0, 1}))
        score += 10.0 * ((c == 1) and (t in {1, 2}))
        score += 7.5 * hashed
        return "completed", round(min(score, 99.9), 2), None
