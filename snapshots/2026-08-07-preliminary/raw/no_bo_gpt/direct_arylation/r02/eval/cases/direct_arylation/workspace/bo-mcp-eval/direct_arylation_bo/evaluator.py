from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .space import Candidate, normalize_candidate


@dataclass
class OracleEvaluator:
    base_url: str
    timeout_seconds: float = 30.0
    max_workers: int = 4

    @classmethod
    def from_environment(cls) -> "OracleEvaluator":
        base_url = os.environ.get("DIRECT_ARYLATION_API_URL", "").strip()
        if not base_url:
            raise RuntimeError("DIRECT_ARYLATION_API_URL is not set.")
        return cls(base_url=base_url.rstrip("/"))

    def _request(self, candidate: Candidate) -> dict[str, Any]:
        normalized = normalize_candidate(candidate)
        payload = json.dumps(normalized).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/v1/evaluate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                parsed = json.loads(body)
                value = float(parsed["yield"])
                return {
                    "parameter_values": normalized,
                    "status": "success",
                    "objective_values": {"yield": value},
                }
        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
            except Exception:
                error_body = ""
            return {
                "parameter_values": normalized,
                "status": "failed",
                "failure_reason": f"HTTP {exc.code}: {error_body.strip() or exc.reason}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "parameter_values": normalized,
                "status": "failed",
                "failure_reason": f"{type(exc).__name__}: {exc}",
            }

    def evaluate_batch(self, candidates: list[Candidate]) -> list[dict[str, Any]]:
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(candidates) or 1)) as executor:
            return list(executor.map(self._request, candidates))


@dataclass
class SyntheticSmokeEvaluator:
    def evaluate_batch(self, candidates: list[Candidate]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for candidate in candidates:
            c = normalize_candidate(candidate)
            score = 10.0
            score += {
                "Potassium acetate": 7.0,
                "Potassium pivalate": 14.0,
                "Cesium acetate": 11.0,
                "Cesium pivalate": 19.0,
            }[c["base"]]
            score += {
                "BrettPhos": 5.0,
                "Di-tert-butylphenylphosphine": 9.0,
                "(t-Bu)PhCPhos": 17.0,
                "Tricyclohexylphosphine": 3.0,
                "PPh3": 2.0,
                "XPhos": 12.0,
                "P(2-furyl)3": 1.0,
                "Methyldiphenylphosphine": 4.0,
                "1268824-69-6": 11.5,
                "JackiePhos": 8.5,
                "SCHEMBL15068049": 7.5,
                "Me2PPh": 6.0,
            }[c["ligand"]]
            score += {
                "DMAc": 11.0,
                "Butyornitrile": 7.5,
                "Butyl Ester": 2.5,
                "p-Xylene": 6.0,
            }[c["solvent"]]
            score += {0.057: 4.0, 0.1: 9.0, 0.153: 6.0}[c["concentration"]]
            score += {90: 2.0, 105: 8.0, 120: 10.5}[c["temperature_c"]]
            if c["base"] == "Cesium pivalate" and c["ligand"] in {"(t-Bu)PhCPhos", "XPhos"}:
                score += 9.0
            if c["solvent"] == "DMAc" and c["temperature_c"] == 120:
                score += 5.0
            results.append(
                {
                    "parameter_values": c,
                    "status": "success",
                    "objective_values": {"yield": round(min(score, 99.0), 2)},
                }
            )
        return results
