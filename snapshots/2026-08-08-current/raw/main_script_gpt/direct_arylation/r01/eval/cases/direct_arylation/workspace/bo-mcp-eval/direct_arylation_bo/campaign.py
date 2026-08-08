from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import logfire
import requests
from domains.bo_mcp.client import BoMcpClient

from .oracle import OracleError, evaluate_candidate

MARKER = "akg-eval-98f2c9514731447aa0f0f60f1a2c44dd"
OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"
DEFAULT_BACKEND = "baybe"
DEFAULT_BATCH_SIZE = 1
DEFAULT_INITIAL_DESIGN_SIZE = 12
DEFAULT_MAX_ATTEMPTS = 60
DEFAULT_RANDOM_SEED = int("a39e5c1b", 16) % (2**31)

BASE_OPTIONS = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]
LIGAND_OPTIONS = [
    "BrettPhos",
    "Di-tert-butylphenylphosphine",
    "(t-Bu)PhCPhos",
    "Tricyclohexylphosphine",
    "PPh3",
    "XPhos",
    "P(2-furyl)3",
    "Methyldiphenylphosphine",
    "1268824-69-6",
    "JackiePhos",
    "SCHEMBL15068049",
    "Me2PPh",
]
SOLVENT_OPTIONS = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]
CONCENTRATION_OPTIONS = [0.057, 0.1, 0.153]
TEMPERATURE_OPTIONS = [90, 105, 120]


@dataclass
class RunArtifacts:
    artifact_dir: Path
    attempts_jsonl: Path
    attempts_json: Path
    summary_json: Path
    export_csv: Path
    smoke_json: Path


class CampaignError(RuntimeError):
    """Raised when campaign state or server responses are unsuitable."""


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_parameter_values(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": str(raw["base"]),
        "ligand": str(raw["ligand"]),
        "solvent": str(raw["solvent"]),
        "concentration": float(raw["concentration"]),
        "temperature_c": int(raw["temperature_c"]),
    }


def build_intake(*, campaign_name: str, backend: str, batch_size: int, initial_design_size: int, max_attempts: int, random_seed: int) -> dict[str, Any]:
    return {
        "name": campaign_name,
        "description": (
            "Direct arylation reaction-yield optimization over the fixed 1,728-point benchmark search space. "
            f"Marker={MARKER}. Objective={OBJECTIVE_NAME} ({OBJECTIVE_UNIT}), maximize. "
            "Sequential BO with discrete/categorical inputs and a 60-attempt benchmark budget."
        ),
        "backend": backend,
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "max_observations": max_attempts,
        "random_seed": random_seed,
        "parameters": [
            {"name": "base", "type": "categorical", "categories": BASE_OPTIONS},
            {"name": "ligand", "type": "categorical", "categories": LIGAND_OPTIONS},
            {"name": "solvent", "type": "categorical", "categories": SOLVENT_OPTIONS},
            {"name": "concentration", "type": "discrete", "values": CONCENTRATION_OPTIONS},
            {"name": "temperature_c", "type": "discrete", "values": TEMPERATURE_OPTIONS},
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


def create_artifact_paths(artifact_root: Path, *, label: str) -> RunArtifacts:
    artifact_dir = artifact_root / f"direct_arylation_bo_{label}_{_now_stamp()}"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return RunArtifacts(
        artifact_dir=artifact_dir,
        attempts_jsonl=artifact_dir / "attempts.jsonl",
        attempts_json=artifact_dir / "attempts.json",
        summary_json=artifact_dir / "summary.json",
        export_csv=artifact_dir / "campaign_export.csv",
        smoke_json=artifact_dir / "smoke_test.json",
    )


def write_manifest(*, root: Path, artifact_dir: Path, run_entrypoint: str, campaign_id: str | None) -> None:
    manifest = {
        "package_modules": [
            "direct_arylation_bo.__init__",
            "direct_arylation_bo.campaign",
            "direct_arylation_bo.oracle",
        ],
        "run_entrypoint": run_entrypoint,
        "latest_artifact_dir": str(artifact_dir),
        "latest_campaign_id": campaign_id,
    }
    (root / "campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def validate_or_raise(client: BoMcpClient, intake: dict[str, Any]) -> None:
    validation = client.validate_intake(intake)
    if not validation.get("valid", False):
        raise CampaignError(f"Campaign intake validation failed: {validation.get('errors', [])}")
    logfire.info("validated intake", warnings=validation.get("warnings", []))


def _resume_if_needed(client: BoMcpClient, campaign_id: str, max_attempts: int) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    if MARKER not in campaign["name"]:
        raise CampaignError(f"Campaign {campaign_id} does not contain required marker {MARKER}")
    status = str(campaign["status"]).lower()
    logfire.info("loaded existing campaign", campaign_id=campaign_id, status=status)
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
    elif status == "completed":
        existing_results = client.get_results(campaign_id)
        if len(existing_results) < max_attempts:
            client.lifecycle(campaign_id, action="reopen")
    elif status in {"created", "running"}:
        pass
    else:
        raise CampaignError(f"Unsupported campaign status for continuation: {status}")
    return client.get_campaign(campaign_id)


def ensure_campaign(
    client: BoMcpClient,
    *,
    campaign_id: str | None,
    backend: str,
    batch_size: int,
    initial_design_size: int,
    max_attempts: int,
    random_seed: int,
    smoke_mode: bool,
) -> dict[str, Any]:
    if campaign_id:
        return _resume_if_needed(client, campaign_id, max_attempts)
    mode = "smoke" if smoke_mode else "run"
    name = f"da-{mode}-{_now_stamp()}-{MARKER}"
    intake = build_intake(
        campaign_name=name,
        backend=backend,
        batch_size=batch_size,
        initial_design_size=initial_design_size,
        max_attempts=max_attempts,
        random_seed=random_seed,
    )
    validate_or_raise(client, intake)
    created = client.create_campaign(intake, idempotency_key=str(uuid.uuid4()))
    created_id = created["campaign_id"]
    logfire.info("created campaign", campaign_id=created_id, name=name)
    return client.get_campaign(created_id)


def _query_pending(client: BoMcpClient, campaign_id: str) -> list[dict[str, Any]]:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
    return sorted(pending, key=lambda row: row.get("created_at", ""))


def get_one_suggestion(client: BoMcpClient, campaign_id: str) -> tuple[dict[str, Any], str]:
    pending = _query_pending(client, campaign_id)
    if pending:
        return pending[0], "pending_reuse"
    try:
        response = client.generate_suggestions(campaign_id, batch_size=1, timeout_s=900.0)
        suggestions = response.get("suggestions", [])
        if suggestions:
            return suggestions[0], "generated"
    except Exception as exc:  # pragma: no cover - recovery path
        logfire.info("generate_suggestions raised; checking pending suggestions", error=str(exc))
        pending = _query_pending(client, campaign_id)
        if pending:
            return pending[0], "pending_after_exception"
        raise
    raise CampaignError("No suggestion available from pending queue or generation response.")


def update_suggestion_status(suggestion_id: str, *, status: str) -> dict[str, Any]:
    base_url = os.environ["BO_MCP_API_URL"].rstrip("/")
    api_key = os.environ["BO_MCP_API_KEY"]
    response = requests.post(
        f"{base_url}/api/v1/suggestions/{suggestion_id}/status",
        headers={"X-API-Key": api_key},
        json={"status": status},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise CampaignError(f"Suggestion status update failed: {payload}")
    return payload


def append_attempt(path: Path, attempt: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(attempt, sort_keys=True) + "\n")


def finalize_campaign(client: BoMcpClient, campaign_id: str, *, artifact_paths: RunArtifacts) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    status = str(campaign["status"]).lower()
    if status in {"running", "created"}:
        client.lifecycle(campaign_id, action="pause")
        campaign = client.get_campaign(campaign_id)
    export_bytes, _mime = client.export_campaign(campaign_id, fmt="csv")
    artifact_paths.export_csv.write_bytes(export_bytes)
    return campaign


def _best_success(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    successes = [row for row in attempts if row["status"] == "success"]
    if not successes:
        return None
    return max(successes, key=lambda row: row["objective_values"][OBJECTIVE_NAME])


def run_campaign(
    *,
    workspace_root: Path,
    artifact_root: Path,
    campaign_id: str | None = None,
    smoke_test: bool = False,
    backend: str = DEFAULT_BACKEND,
    batch_size: int = DEFAULT_BATCH_SIZE,
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> dict[str, Any]:
    if batch_size != 1:
        raise CampaignError("This benchmark runner is intentionally sequential; use batch_size=1.")
    client = BoMcpClient.from_env(timeout_s=120.0)
    artifact_paths = create_artifact_paths(artifact_root, label="smoke" if smoke_test else "run")

    campaign = ensure_campaign(
        client,
        campaign_id=campaign_id,
        backend=backend,
        batch_size=batch_size,
        initial_design_size=initial_design_size,
        max_attempts=max_attempts,
        random_seed=random_seed,
        smoke_mode=smoke_test,
    )
    current_campaign_id = campaign["id"]
    write_manifest(
        root=workspace_root,
        artifact_dir=artifact_paths.artifact_dir,
        run_entrypoint="run_direct_arylation_bo.py",
        campaign_id=current_campaign_id,
    )

    if smoke_test:
        decision = client.next_action(current_campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            raise CampaignError(f"Unexpected smoke-test next_action response: {decision}")
        suggestion, source = get_one_suggestion(client, current_campaign_id)
        smoke_payload = {
            "campaign_id": current_campaign_id,
            "campaign_name": campaign["name"],
            "next_action": decision,
            "suggestion_source": source,
            "suggestion_id": suggestion["suggestion_id"],
            "parameter_values": normalize_parameter_values(suggestion["parameter_values"]),
            "status": "smoke_test_pending_suggestion_created",
            "timestamp_utc": _utc_now_iso(),
        }
        artifact_paths.smoke_json.write_text(json.dumps(smoke_payload, indent=2), encoding="utf-8")
        final_campaign = finalize_campaign(client, current_campaign_id, artifact_paths=artifact_paths)
        summary = {
            "mode": "smoke_test",
            "campaign_id": current_campaign_id,
            "campaign_name": campaign["name"],
            "campaign_status": final_campaign["status"],
            "artifact_dir": str(artifact_paths.artifact_dir),
            "smoke_payload": smoke_payload,
        }
        artifact_paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    existing_results = client.get_results(current_campaign_id)
    assumed_attempts_so_far = len(existing_results)
    remaining_attempt_budget = max(0, max_attempts - assumed_attempts_so_far)
    logfire.info(
        "starting production loop",
        campaign_id=current_campaign_id,
        existing_results=len(existing_results),
        remaining_attempt_budget=remaining_attempt_budget,
    )

    attempts: list[dict[str, Any]] = []
    successful_evaluations = 0
    attempted_evaluations = 0

    while attempted_evaluations < remaining_attempt_budget:
        pending = _query_pending(client, current_campaign_id)
        if pending:
            suggestion, suggestion_source = pending[0], "pending_reuse"
        else:
            decision = client.next_action(current_campaign_id)
            if decision.get("action") != "bo_generate_suggestions":
                logfire.info("server advised stop", decision=decision)
                break
            suggestion, suggestion_source = get_one_suggestion(client, current_campaign_id)
        parameter_values = normalize_parameter_values(suggestion["parameter_values"])
        attempt_number = assumed_attempts_so_far + attempted_evaluations + 1
        attempt_record: dict[str, Any] = {
            "attempt_index": attempt_number,
            "campaign_id": current_campaign_id,
            "timestamp_utc": _utc_now_iso(),
            "status": "failed",
            "parameter_values": parameter_values,
            "objective_values": None,
            "objective_name": OBJECTIVE_NAME,
            "objective_unit": OBJECTIVE_UNIT,
            "suggestion_id": suggestion["suggestion_id"],
            "suggestion_status_before_evaluation": suggestion["status"],
            "suggestion_source": suggestion_source,
            "iteration": suggestion.get("provenance", {}).get("iteration"),
        }

        attempted_evaluations += 1
        try:
            measured_yield = evaluate_candidate(parameter_values)
            submit_response = client.submit_results(
                current_campaign_id,
                results=[
                    {
                        "parameter_values": parameter_values,
                        "objective_values": {OBJECTIVE_NAME: measured_yield},
                        "suggestion_id": suggestion["suggestion_id"],
                        "metadata": {
                            "experiment_id": f"direct_arylation_attempt_{attempt_number}",
                            "notes": "Direct arylation benchmark oracle evaluation.",
                        },
                    }
                ],
                idempotency_key=str(uuid.uuid4()),
                force=True,
            )
            attempt_record.update(
                {
                    "status": "success",
                    "objective_values": {OBJECTIVE_NAME: measured_yield},
                    "bo_result_ids": submit_response.get("result_ids", []),
                }
            )
            successful_evaluations += 1
            print(
                f"attempt {attempt_number:02d}/60 success yield={measured_yield:.2f}% | "
                f"base={parameter_values['base']} | ligand={parameter_values['ligand']} | "
                f"solvent={parameter_values['solvent']} | concentration={parameter_values['concentration']} | "
                f"temperature_c={parameter_values['temperature_c']}"
            )
        except OracleError as exc:
            attempt_record["error"] = str(exc)
            try:
                update_suggestion_status(suggestion["suggestion_id"], status="rejected")
                attempt_record["post_failure_suggestion_status"] = "rejected"
            except Exception as status_exc:  # pragma: no cover - secondary failure path
                attempt_record["status_update_error"] = str(status_exc)
            print(
                f"attempt {attempt_number:02d}/60 failed error={exc} | "
                f"base={parameter_values['base']} | ligand={parameter_values['ligand']} | "
                f"solvent={parameter_values['solvent']} | concentration={parameter_values['concentration']} | "
                f"temperature_c={parameter_values['temperature_c']}"
            )
        append_attempt(artifact_paths.attempts_jsonl, attempt_record)
        attempts.append(attempt_record)

    final_campaign = finalize_campaign(client, current_campaign_id, artifact_paths=artifact_paths)
    best = _best_success(attempts)
    summary = {
        "mode": "production",
        "campaign_id": current_campaign_id,
        "campaign_name": campaign["name"],
        "campaign_status": final_campaign["status"],
        "backend": backend,
        "design": {
            "batch_size": batch_size,
            "initial_design_size": initial_design_size,
            "max_attempts": max_attempts,
            "max_observations": max_attempts,
            "random_seed": random_seed,
        },
        "successful_evaluations": successful_evaluations,
        "attempted_evaluations": attempted_evaluations,
        "best_result": best,
        "artifact_dir": str(artifact_paths.artifact_dir),
        "attempts": attempts,
    }
    artifact_paths.attempts_json.write_text(json.dumps(attempts, indent=2), encoding="utf-8")
    artifact_paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_manifest(
        root=workspace_root,
        artifact_dir=artifact_paths.artifact_dir,
        run_entrypoint="run_direct_arylation_bo.py",
        campaign_id=current_campaign_id,
    )
    return summary
