from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient

from .oracle import DirectArylationOracle, OracleError
from .space import (
    CACHE_BUSTER_NONCE,
    INVOCATION_MARKER,
    OBJECTIVE_NAME,
    build_campaign_name,
    build_intake,
)


@dataclass
class RunOutcome:
    campaign_id: str
    artifact_dir: Path
    attempts_used: int
    successful_attempts: int
    best_attempt: dict[str, Any] | None
    attempts: list[dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _normalize_parameter_values(parameter_values: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": str(parameter_values["base"]),
        "ligand": str(parameter_values["ligand"]),
        "solvent": str(parameter_values["solvent"]),
        "concentration": float(parameter_values["concentration"]),
        "temperature_c": int(round(float(parameter_values["temperature_c"]))),
    }


def _load_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    successful = [a for a in attempts if a["status"] == "success"]
    if not successful:
        return None
    return max(successful, key=lambda a: float(a["objective_values"][OBJECTIVE_NAME]))


def _campaign_name_from_record(campaign_record: dict[str, Any]) -> str:
    for key in ("name", "campaign_name"):
        value = campaign_record.get(key)
        if isinstance(value, str):
            return value
    spec = campaign_record.get("spec")
    if isinstance(spec, dict):
        value = spec.get("name")
        if isinstance(value, str):
            return value
    raise RuntimeError(f"Could not determine campaign name from record keys={sorted(campaign_record.keys())}")


def _ensure_campaign_marker(client: BoMcpClient, campaign_id: str) -> None:
    campaign_record = client.get_campaign(campaign_id)
    name = _campaign_name_from_record(campaign_record)
    if INVOCATION_MARKER not in name:
        raise RuntimeError(
            f"Refusing to use campaign {campaign_id!r}; required marker {INVOCATION_MARKER!r} not found in name {name!r}"
        )


def _create_or_resume_campaign(client: BoMcpClient, campaign_id: str | None, random_seed: int) -> str:
    if campaign_id:
        _ensure_campaign_marker(client, campaign_id)
        campaign_record = client.get_campaign(campaign_id)
        status = str(campaign_record.get("status", "")).lower()
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            logfire.info("Resumed paused campaign", campaign_id=campaign_id)
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            logfire.info("Reopened completed campaign", campaign_id=campaign_id)
        else:
            logfire.info("Using existing campaign", campaign_id=campaign_id, status=status)
        return campaign_id

    name = build_campaign_name()
    intake = build_intake(name=name, random_seed=random_seed)
    validation = client.validate_intake(intake)
    if not validation.get("valid"):
        raise RuntimeError(f"Campaign intake invalid: {validation}")
    create_response = client.create_campaign(
        intake,
        idempotency_key=BoMcpClient.make_idempotency_key("direct-arylation-create", name, CACHE_BUSTER_NONCE),
    )
    created_campaign_id = create_response["campaign_id"]
    _ensure_campaign_marker(client, created_campaign_id)
    logfire.info("Created campaign", campaign_id=created_campaign_id, campaign_name=name)
    return created_campaign_id


def run_campaign(
    *,
    campaign_id: str | None,
    artifact_dir: Path,
    max_attempts: int,
    random_seed: int,
    oracle_timeout_s: float,
) -> RunOutcome:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    attempts_path = artifact_dir / "attempts.jsonl"

    client = BoMcpClient.from_env(timeout_s=120.0)
    oracle = DirectArylationOracle(timeout_s=oracle_timeout_s)
    active_campaign_id = _create_or_resume_campaign(client, campaign_id, random_seed)

    _write_json(
        artifact_dir / "run_metadata.json",
        {
            "campaign_id": active_campaign_id,
            "cache_buster_nonce": CACHE_BUSTER_NONCE,
            "invocation_marker": INVOCATION_MARKER,
            "max_attempts_this_invocation": max_attempts,
            "random_seed": random_seed,
            "started_at": _utc_now(),
        },
    )

    attempts_used = 0
    try:
        while attempts_used < max_attempts:
            decision = client.next_action(active_campaign_id)
            action = decision.get("action")
            logfire.info(
                "Next action",
                campaign_id=active_campaign_id,
                action=action,
                attempts_used=attempts_used,
                max_attempts=max_attempts,
            )
            if action != "bo_generate_suggestions":
                break

            generation = client.generate_suggestions(active_campaign_id, batch_size=1, timeout_s=900.0)
            suggestions = generation.get("suggestions", [])
            if not suggestions:
                raise RuntimeError(f"Suggestion generation returned no suggestions: {generation}")
            suggestion = suggestions[0]
            parameter_values = _normalize_parameter_values(suggestion["parameter_values"])
            attempt_index = len(_load_attempts(attempts_path)) + 1
            attempts_used += 1

            attempt_record: dict[str, Any] = {
                "attempt_index": attempt_index,
                "campaign_id": active_campaign_id,
                "suggestion_id": suggestion["suggestion_id"],
                "parameter_values": parameter_values,
                "objective_values": None,
                "status": "started",
                "oracle_status": None,
                "submitted_to_bo_mcp": False,
                "started_at": _utc_now(),
            }

            try:
                measured_yield = oracle.evaluate(parameter_values)
                attempt_record["objective_values"] = {OBJECTIVE_NAME: measured_yield}
                attempt_record["status"] = "success"
                attempt_record["oracle_status"] = "success"
                submit_response = client.submit_results(
                    active_campaign_id,
                    results=[
                        {
                            "suggestion_id": suggestion["suggestion_id"],
                            "parameter_values": parameter_values,
                            "objective_values": {OBJECTIVE_NAME: measured_yield},
                            "metadata": {
                                "notes": (
                                    "Direct arylation benchmark evaluation via oracle service; "
                                    f"attempt_index={attempt_index}; nonce={CACHE_BUSTER_NONCE}"
                                )
                            },
                        }
                    ],
                    idempotency_key=BoMcpClient.make_idempotency_key(
                        "direct-arylation-submit", active_campaign_id, str(attempt_index)
                    ),
                    force=True,
                )
                attempt_record["submitted_to_bo_mcp"] = True
                attempt_record["submit_response"] = {
                    "success": submit_response.get("success"),
                    "result_ids": submit_response.get("result_ids", []),
                    "warnings": submit_response.get("warnings", []),
                }
                print(
                    f"attempt {attempt_index}/{max_attempts}: success yield={measured_yield:.2f}% "
                    f"params={parameter_values}"
                )
            except OracleError as exc:
                attempt_record["status"] = "failed"
                attempt_record["oracle_status"] = "failed"
                attempt_record["error"] = str(exc)
                try:
                    update_response = client.update_suggestion_status(suggestion["suggestion_id"], "expired")
                    attempt_record["suggestion_status_update"] = update_response
                except Exception as update_exc:  # pragma: no cover - best effort provenance
                    attempt_record["suggestion_status_update_error"] = str(update_exc)
                print(f"attempt {attempt_index}/{max_attempts}: failed params={parameter_values} error={exc}")
            finally:
                attempt_record["finished_at"] = _utc_now()
                _append_jsonl(attempts_path, attempt_record)

        diagnostics = None
        try:
            diagnostics = client.get_diagnostics(active_campaign_id, verbosity="standard", timeout_s=600.0)
            _write_json(artifact_dir / "diagnostics.json", diagnostics)
        except Exception as exc:  # pragma: no cover - best effort provenance
            _write_json(artifact_dir / "diagnostics_error.json", {"error": str(exc), "captured_at": _utc_now()})

        results = client.get_results(active_campaign_id)
        _write_json(artifact_dir / "bo_results.json", {"results": results})
        campaign_record = client.get_campaign(active_campaign_id)
        _write_json(artifact_dir / "campaign_record.json", campaign_record)

        attempts = _load_attempts(attempts_path)
        best_attempt = _best_attempt(attempts)
        summary = {
            "campaign_id": active_campaign_id,
            "attempted_evaluations": len(attempts),
            "successful_evaluations": sum(1 for a in attempts if a["status"] == "success"),
            "failed_evaluations": sum(1 for a in attempts if a["status"] != "success"),
            "best_attempt": best_attempt,
            "diagnostics_present": diagnostics is not None,
            "updated_at": _utc_now(),
        }
        _write_json(artifact_dir / "summary.json", summary)
        return RunOutcome(
            campaign_id=active_campaign_id,
            artifact_dir=artifact_dir,
            attempts_used=attempts_used,
            successful_attempts=summary["successful_evaluations"],
            best_attempt=best_attempt,
            attempts=attempts,
        )
    finally:
        try:
            client.lifecycle(active_campaign_id, action="pause")
            logfire.info("Paused campaign", campaign_id=active_campaign_id)
        except Exception as exc:  # pragma: no cover - best effort provenance
            _write_json(
                artifact_dir / "pause_error.json",
                {"campaign_id": active_campaign_id, "error": str(exc), "captured_at": _utc_now()},
            )
