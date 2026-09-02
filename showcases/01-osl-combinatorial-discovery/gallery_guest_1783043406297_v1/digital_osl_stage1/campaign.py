from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .config import Stage1Config
from .evaluation import evaluate_candidate, result_to_jsonable
from .fragments import build_plain_categorical_intake, prepare_stage
from .reporting import append_jsonl, concise_preview_text, ensure_dir, write_csv, write_export, write_json, write_text


def _bo_validate_if_available(prepared, allow_fallback: bool) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
    config = prepared.config
    if not config.validate_with_bo_api:
        return None, prepared.intake, prepared.intake_backend
    try:
        client = BoMcpClient.from_env()
    except Exception as exc:  # noqa: BLE001
        return {"warning": f"Skipped BO validate_intake: {exc}"}, prepared.intake, prepared.intake_backend

    try:
        response = client.validate_intake(prepared.intake)
        return response, prepared.intake, prepared.intake_backend
    except Exception as exc:  # noqa: BLE001
        if not allow_fallback:
            raise
        fallback_intake, fallback_backend = build_plain_categorical_intake(
            config,
            prepared.active_caps,
            prepared.active_bridges,
            prepared.active_cores,
        )
        fallback_response = client.validate_intake(fallback_intake)
        return {
            "warning": f"BayBE custom validate_intake failed and plain-categorical fallback validated instead: {exc}",
            "fallback_validation": fallback_response,
        }, fallback_intake, fallback_backend


def _write_prepared_artifacts(prepared, validation_response: dict[str, Any] | None) -> None:
    artifact_dir = ensure_dir(prepared.config.artifact_dir)
    write_json(artifact_dir / "run_config.json", prepared.config.to_jsonable_dict())
    write_json(artifact_dir / "assembly_validation.json", prepared.validation_report)
    write_csv(artifact_dir / "active_caps.csv", prepared.active_caps)
    write_csv(artifact_dir / "active_bridges.csv", prepared.active_bridges)
    write_csv(artifact_dir / "active_cores.csv", prepared.active_cores)
    write_csv(artifact_dir / "candidate_library.csv", prepared.candidate_library)
    write_json(artifact_dir / "initial_candidates.json", prepared.initial_candidates)
    write_json(artifact_dir / "campaign_intake.json", prepared.preview_summary["intake"])
    write_json(artifact_dir / "preview_summary.json", prepared.preview_summary)
    if validation_response is not None:
        write_json(artifact_dir / "validate_intake_response.json", validation_response)
    write_text(artifact_dir / "PREVIEW.txt", concise_preview_text(prepared.preview_summary))


def _candidate_lookup(prepared) -> dict[str, dict[str, Any]]:
    return {row["candidate_id"]: row for row in prepared.candidate_library.to_dict(orient="records")}


def _candidate_from_parameter_values(prepared, parameter_values: dict[str, Any]) -> dict[str, Any]:
    candidate_id = f"{parameter_values['cap_id']}{parameter_values['bridge_id']}{parameter_values['core_id']}"
    lookup = _candidate_lookup(prepared)
    if candidate_id not in lookup:
        raise KeyError(f"Suggested candidate {candidate_id} is outside the prepared active library")
    return lookup[candidate_id]


def _persist_campaign_event(path: Path, payload: dict[str, Any]) -> None:
    append_jsonl(path, payload)


def _is_terminal_generation_rejection(exc: Exception) -> bool:
    if isinstance(exc, BoMcpOperationError):
        message = str(exc).lower()
        return any(
            token in message
            for token in [
                "stopping criteria",
                "max_iterations",
                "max_observations",
                "already been met",
                "no further suggestions",
            ]
        )
    return False


def _ensure_campaign_ready(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    campaign = client.get_campaign(campaign_id)
    status = str(campaign.get("status", "")).lower()
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        campaign = client.get_campaign(campaign_id)
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        campaign = client.get_campaign(campaign_id)
    return campaign


def _create_or_attach_campaign(prepared, intake: dict[str, Any], artifact_dir: Path) -> tuple[BoMcpClient, str]:
    client = BoMcpClient.from_env()
    if prepared.config.campaign_id:
        campaign_id = prepared.config.campaign_id
        campaign = _ensure_campaign_ready(client, campaign_id)
        write_json(artifact_dir / "attached_campaign.json", campaign)
        return client, campaign_id

    idempotency_key = client.make_idempotency_key("create", prepared.config.campaign_name, prepared.config.run_label or "run")
    response = client.create_campaign(intake, idempotency_key=idempotency_key)
    write_json(artifact_dir / "campaign_create_response.json", response)
    campaign_id = response["campaign_id"]
    campaign = client.get_campaign(campaign_id)
    write_json(artifact_dir / "created_campaign.json", campaign)
    return client, campaign_id


def _submit_success(client: BoMcpClient, campaign_id: str, result_payload: dict[str, Any], run_label: str) -> dict[str, Any]:
    key = client.make_idempotency_key("submit", campaign_id, result_payload["parameter_values"]["cap_id"], result_payload["parameter_values"]["bridge_id"], result_payload["parameter_values"]["core_id"], run_label)
    return client.submit_results(campaign_id, results=[result_payload], idempotency_key=key)


def _record_diagnostics(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> dict[str, Any]:
    diagnostics = client.get_diagnostics(campaign_id, verbosity="standard")
    append_jsonl(artifact_dir / "diagnostics_history.jsonl", diagnostics)
    return diagnostics


def _seed_if_needed(prepared, client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> int:
    diagnostics = _record_diagnostics(client, campaign_id, artifact_dir)
    existing_results = int(diagnostics.get("n_results") or 0)
    if existing_results > 0:
        return 0
    successes = 0
    for candidate in prepared.initial_candidates:
        if successes >= prepared.config.max_successful_evaluations:
            break
        result = evaluate_candidate(candidate, prepared.config)
        result.metadata["evaluation_stage"] = "initial_seed"
        if result.success and result.objective_values:
            submit_response = _submit_success(client, campaign_id, result.to_result_row(), prepared.config.run_label or "run")
            payload = result_to_jsonable(result)
            payload["submit_response"] = submit_response
            append_jsonl(artifact_dir / "results_success.jsonl", payload)
            successes += 1
        else:
            append_jsonl(artifact_dir / "results_failures.jsonl", result_to_jsonable(result))
    return successes


def _acquire_suggestions(client: BoMcpClient, campaign_id: str, batch_size: int, artifact_dir: Path) -> list[dict[str, Any]]:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=batch_size)
    if pending:
        for suggestion in pending:
            append_jsonl(artifact_dir / "suggestions.jsonl", {"source": "pending", **suggestion})
        return pending[:batch_size]

    decision = client.next_action(campaign_id)
    append_jsonl(artifact_dir / "loop_decisions.jsonl", decision)
    if decision.get("action") != "bo_generate_suggestions":
        return []
    response = client.generate_suggestions(campaign_id, batch_size=batch_size)
    suggestions = response.get("suggestions", [])
    for suggestion in suggestions:
        append_jsonl(artifact_dir / "suggestions.jsonl", {"source": "generated", **suggestion})
    return suggestions


def _pause_or_terminate(client: BoMcpClient, campaign_id: str, terminate_on_exit: bool, artifact_dir: Path) -> None:
    campaign = client.get_campaign(campaign_id)
    write_json(artifact_dir / "final_campaign_state.json", campaign)
    status = str(campaign.get("status", "")).lower()
    if terminate_on_exit:
        response = client.lifecycle(campaign_id, action="terminate")
        write_json(artifact_dir / "lifecycle_on_exit.json", response)
        return
    if status == "running":
        response = client.lifecycle(campaign_id, action="pause")
        write_json(artifact_dir / "lifecycle_on_exit.json", response)


def _run_execute_mode(prepared, intake: dict[str, Any], intake_backend: str) -> int:
    config = prepared.config
    artifact_dir = ensure_dir(config.artifact_dir)
    client, campaign_id = _create_or_attach_campaign(prepared, intake, artifact_dir)
    write_json(artifact_dir / "campaign_runtime.json", {"campaign_id": campaign_id, "intake_backend": intake_backend})

    started = time.time()
    successes = _seed_if_needed(prepared, client, campaign_id, artifact_dir)
    seen_candidates = {candidate["candidate_id"] for candidate in prepared.initial_candidates}

    while successes < config.max_successful_evaluations:
        elapsed_minutes = (time.time() - started) / 60.0
        if elapsed_minutes >= config.max_runtime_minutes:
            logfire.info("Stopping because invocation wall-clock budget was reached", elapsed_minutes=elapsed_minutes)
            break
        diagnostics = _record_diagnostics(client, campaign_id, artifact_dir)
        logfire.info(
            "Campaign diagnostics",
            campaign_id=campaign_id,
            n_results=diagnostics.get("n_results"),
            n_pending_suggestions=diagnostics.get("n_pending_suggestions"),
            iteration=diagnostics.get("iteration"),
        )
        try:
            suggestions = _acquire_suggestions(client, campaign_id, config.batch_size, artifact_dir)
        except Exception as exc:  # noqa: BLE001
            if _is_terminal_generation_rejection(exc):
                append_jsonl(artifact_dir / "loop_decisions.jsonl", {"stopping_reason": str(exc)})
                break
            raise
        if not suggestions:
            break

        for suggestion in suggestions:
            parameter_values = suggestion["parameter_values"]
            suggestion_id = suggestion["id"]
            try:
                candidate = _candidate_from_parameter_values(prepared, parameter_values)
            except KeyError as exc:
                client.update_suggestion_status(suggestion_id, "rejected")
                append_jsonl(
                    artifact_dir / "results_failures.jsonl",
                    {
                        "candidate_id": f"{parameter_values['cap_id']}{parameter_values['bridge_id']}{parameter_values['core_id']}",
                        "failure_reason": str(exc),
                        "suggestion_id": suggestion_id,
                    },
                )
                continue
            if candidate["candidate_id"] in seen_candidates:
                client.update_suggestion_status(suggestion_id, "rejected")
                append_jsonl(
                    artifact_dir / "results_failures.jsonl",
                    {
                        "candidate_id": candidate["candidate_id"],
                        "failure_reason": "Duplicate candidate encountered within this invocation",
                        "suggestion_id": suggestion_id,
                    },
                )
                continue
            candidate = dict(candidate)
            candidate["suggestion_id"] = suggestion_id
            result = evaluate_candidate(candidate, config, suggestion_id=suggestion_id)
            result.metadata["evaluation_stage"] = "bo_suggestion"
            if result.success and result.objective_values:
                submit_response = _submit_success(client, campaign_id, result.to_result_row(), config.run_label or "run")
                payload = result_to_jsonable(result)
                payload["submit_response"] = submit_response
                append_jsonl(artifact_dir / "results_success.jsonl", payload)
                successes += 1
                seen_candidates.add(candidate["candidate_id"])
                if successes >= config.max_successful_evaluations:
                    break
            else:
                client.update_suggestion_status(suggestion_id, "rejected")
                append_jsonl(artifact_dir / "results_failures.jsonl", result_to_jsonable(result))

    content, content_type = client.export_campaign(campaign_id, fmt=config.export_format)
    export_path = write_export(artifact_dir / "campaign_export", content, content_type)
    write_json(artifact_dir / "campaign_export_meta.json", {"content_type": content_type, "path": str(export_path)})
    _pause_or_terminate(client, campaign_id, config.terminate_on_exit, artifact_dir)
    print(f"Execution finished for campaign {campaign_id}. Artifacts: {artifact_dir}")
    return 0


def main(config: Stage1Config) -> int:
    prepared = prepare_stage(config)
    validation_response, validated_intake, intake_backend = _bo_validate_if_available(
        prepared,
        allow_fallback=prepared.config.allow_plain_categorical_fallback,
    )
    prepared.preview_summary["validated_intake_backend"] = intake_backend
    if validation_response is not None:
        prepared.preview_summary["bo_validate_response"] = validation_response
        if "fallback_validation" in validation_response:
            prepared.preview_summary["intake"] = validated_intake
        elif validation_response.get("valid") is False:
            _write_prepared_artifacts(prepared, validation_response)
            raise ValueError(f"BO-MCP validate_intake rejected the prepared intake: {validation_response}")
    _write_prepared_artifacts(prepared, validation_response)

    preview_text = concise_preview_text(prepared.preview_summary)
    print(preview_text)
    print(f"Artifacts: {prepared.config.artifact_dir}")
    if not prepared.config.execute:
        print("Preview-only mode: campaign creation and BO execution were skipped.")
        return 0
    return _run_execute_mode(prepared, validated_intake, intake_backend)


def cli_main(argv: list[str] | None = None) -> int:
    from .config import Stage1Config
    from .run_args import parse_args

    args = parse_args(argv)
    config = Stage1Config(**args)
    try:
        return main(config)
    except (BoMcpClientError, BoMcpOperationError) as exc:
        message = str(exc)
        if ", Traceback:" in message:
            message = message.split(", Traceback:", 1)[0]
        print(f"BO-MCP error: {message}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Unhandled error: {exc}", file=sys.stderr)
        return 1
