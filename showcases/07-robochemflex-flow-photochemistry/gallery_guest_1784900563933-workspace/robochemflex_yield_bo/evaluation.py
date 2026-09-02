from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import logfire

from .objectives import extract_yield_percent, objective_values
from .robridge_client import RobridgeClient, wait_for_run
from .space import normalize_candidate, robridge_parameters


@dataclass
class EvalOutcome:
    success: bool
    parameter_values: dict | None = None
    objective_values: dict | None = None
    run_id: str | None = None
    error: str | None = None
    platform_failure: bool = False


def evaluate(
    candidate: dict,
    *,
    mode: str,
    artifact_dir: Path,
    label: str,
    timeout_s: float,
    allow_hardware_retry: bool = False,
) -> EvalOutcome:
    c = normalize_candidate(candidate)
    if mode == "local-simulation":
        y = _synthetic_yield(c)
        _write_json(artifact_dir / "simulated_evaluations.jsonl", {"label": label, "candidate": c, "yield_percent": y})
        return EvalOutcome(True, c, objective_values(c, y))
    return _evaluate_robridge(
        c,
        artifact_dir=artifact_dir,
        label=label,
        timeout_s=timeout_s,
        allow_hardware_retry=allow_hardware_retry,
    )


def _evaluate_robridge(
    candidate: dict,
    *,
    artifact_dir: Path,
    label: str,
    timeout_s: float,
    allow_hardware_retry: bool,
) -> EvalOutcome:
    client = RobridgeClient()
    duplicate = _duplicate_run(client, label)
    if duplicate and duplicate.get("status") in {"queued", "running"}:
        return EvalOutcome(False, run_id=duplicate.get("run_id"), error=f"Existing RoboFlex run {duplicate.get('run_id')} is {duplicate.get('status')} for {label}; refusing duplicate submission.", platform_failure=True)
    if duplicate and not allow_hardware_retry:
        return EvalOutcome(False, run_id=duplicate.get("run_id"), error=f"Existing RoboFlex run {duplicate.get('run_id')} already used sample {label}; pass --allow-hardware-retry with a new --retry-suffix only if a repeat is intentional.", platform_failure=True)

    params = robridge_parameters(candidate, sample_name=label)
    run_id = None
    try:
        submitted = client.submit_run(params, note=f"BO-MCP RoboChemFlex yield optimization {label}")
        run_id = submitted["run"]["run_id"]
        print(f"RoboFlex run submitted: {run_id} ({label})")
        logfire.info("Submitted RoboFlex run", run_id=run_id, label=label)
        record = wait_for_run(client, run_id, timeout_s=timeout_s)
        result = _safe_result(client, run_id)
        failure = _failure_message(record, result)
        if failure:
            _write_json(artifact_dir / "failed_evaluations.jsonl", {"label": label, "run_id": run_id, "candidate": candidate, "record": record, "result": result, "failure": failure})
            return EvalOutcome(False, run_id=run_id, error=failure, platform_failure=True)
        y = extract_yield_percent(result.get("result"))
        actual = _actual_parameters(candidate, result.get("parameters") or [])
        _write_json(artifact_dir / "robridge_results.jsonl", {"label": label, "run_id": run_id, "candidate": candidate, "result": result})
        return EvalOutcome(True, actual, objective_values(actual, y), run_id=run_id)
    except Exception as exc:
        _write_json(artifact_dir / "failed_evaluations.jsonl", {"label": label, "run_id": run_id, "candidate": candidate, "failure": str(exc)})
        return EvalOutcome(False, run_id=run_id, error=str(exc), platform_failure=True)


def _safe_result(client: RobridgeClient, run_id: str) -> dict:
    try:
        return client.result(run_id)
    except Exception as exc:
        return {"run_id": run_id, "status": "unknown", "success": False, "error": f"result fetch failed: {exc}"}


def _failure_message(record: dict, result: dict) -> str | None:
    payload = result.get("result") if isinstance(result, dict) else None
    if record.get("status") == "failed" or record.get("success") is False:
        return record.get("error") or _result_failure(payload) or "RoboFlex run failed"
    if result.get("status") == "failed" or result.get("success") is False:
        return result.get("error") or _result_failure(payload) or "RoboFlex analysis failed"
    return _result_failure(payload)


def _result_failure(payload: object) -> str | None:
    if isinstance(payload, dict) and payload.get("pass") is False:
        return str(payload.get("failure_message") or "analysis result reported pass=false")
    return None


def _duplicate_run(client: RobridgeClient, label: str) -> dict | None:
    try:
        runs = client.list_runs().get("runs", [])
    except Exception:
        return None
    for run in runs:
        note = str(run.get("note") or "")
        sample_names = [p.get("value") for p in run.get("parameters", []) if isinstance(p, dict) and p.get("name") == "sample_name"]
        if label in note or label in sample_names:
            return run
    return None


def _actual_parameters(candidate: dict, parameters: list[dict]) -> dict:
    actual = dict(candidate)
    by_name = {p.get("name"): p for p in parameters if isinstance(p, dict)}
    if "light_intensity" in by_name:
        actual["light_intensity"] = by_name["light_intensity"].get("value", actual["light_intensity"])
    if "residence_time" in by_name:
        actual["residence_time_min"] = float(by_name["residence_time"].get("value", actual["residence_time_min"] * 60.0)) / 60.0
    return normalize_candidate(actual)


def _synthetic_yield(candidate: dict) -> float:
    catalyst_bonus = {"4CzIPN": 12, "Ir CF3 ppy": 10, "Ru bpy PF6": 7, "Ir ppy": 6, "Ru bpy Cl": 4}[candidate["catalyst_type"]]
    oxidant_bonus = 4 if candidate["oxidant_type"] == "4-Ph py NO" else 0
    opt = 72
    opt -= 1800 * (candidate["catalyst_equiv"] - 0.0028) ** 2
    opt -= 5.5 * (candidate["TFAA_equiv"] - 2.3) ** 2
    opt -= 4.5 * (candidate["oxidant_equiv"] - 1.8) ** 2
    opt -= 0.010 * (candidate["residence_time_min"] - 42) ** 2
    opt -= 0.0035 * (candidate["light_intensity"] - 75) ** 2
    digest = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()
    noise = (int(digest[:8], 16) / 0xFFFFFFFF - 0.5) * 3.0
    return max(0.0, min(100.0, opt + catalyst_bonus + oxidant_bonus + noise))


def _write_json(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(_clean(row), sort_keys=True) + "\n")


def _clean(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj
