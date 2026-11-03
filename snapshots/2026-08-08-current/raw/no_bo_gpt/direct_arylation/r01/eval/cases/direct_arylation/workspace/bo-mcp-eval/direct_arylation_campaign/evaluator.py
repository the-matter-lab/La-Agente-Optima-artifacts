from __future__ import annotations

from typing import Dict
import os

import requests

Candidate = Dict[str, object]


class DirectArylationEvaluator:
    def __init__(self, timeout_s: float = 30.0):
        base_url = os.getenv("DIRECT_ARYLATION_API_URL")
        if not base_url:
            raise RuntimeError("DIRECT_ARYLATION_API_URL is not set")
        self.url = base_url.rstrip("/") + "/v1/evaluate"
        self.timeout_s = timeout_s
        self.session = requests.Session()

    def evaluate(self, candidate: Candidate) -> Dict[str, object]:
        payload = {
            "base": candidate["base"],
            "ligand": candidate["ligand"],
            "solvent": candidate["solvent"],
            "concentration": float(candidate["concentration"]),
            "temperature_c": int(candidate["temperature_c"]),
        }
        try:
            response = self.session.post(self.url, json=payload, timeout=self.timeout_s)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "failure_reason": f"request_exception: {type(exc).__name__}: {exc}",
            }
        if not response.ok:
            text = response.text.strip().replace("\n", " ")[:400]
            return {
                "status": "failed",
                "failure_reason": f"http_{response.status_code}: {text}",
            }
        try:
            data = response.json()
            value = float(data["yield"])
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "failure_reason": f"invalid_json: {type(exc).__name__}: {exc}",
            }
        return {
            "status": "success",
            "objective_values": {"yield": value},
        }
