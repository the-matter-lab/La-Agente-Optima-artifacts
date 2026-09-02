from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import logfire
import requests
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError
from digital_osl_stage1.fragments import build_plain_categorical_intake

from .config import Stage1bConfig
from .evaluation import evaluate_candidate, result_to_jsonable
from .legacy_import import existing_campaign_candidate_ids_from_export, import_rows_as_frame
from .reporting import append_jsonl, concise_preview_text, ensure_dir, write_csv, write_export, write_json, write_text
from .search_space import prepare_stage


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
    write_json(artifact_dir / "legacy_import_plan.json", prepared.legacy_import_summary)
    write_csv(artifact_dir / "legacy_import_rows.csv", import_rows_as_frame(prepared.legacy_import_rows))
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
    key = client.make_idempotency_key(
        "submit",
        campaign_id,
        result_payload["parameter_values"]["cap_id"],
        result_payload["parameter_values"]["bridge_id"],
        result_payload["parameter_values"]["core_id"],
        run_label,
    )
    return client.submit_results(campaign_id, results=[result_payload], idempotency_key=key)


def _is_read_timeout(exc: Exception) -> bool:
    return isinstance(exc, requests.exceptions.Timeout) or "read timed out" in str(exc).lower()


def _record_runtime_warning(artifact_dir: Path, *, operation: str, message: str, error: Exception) -> None:
    append_jsonl(
        artifact_dir / "runtime_warnings.jsonl",
        {"operation": operation, "message": message, "error": str(error)},
    )


def _call_with_timeout_retries(
    operation: str,
    func,
    *,
    artifact_dir: Path,
    max_attempts: int = 3,
    continue_on_timeout: bool = False,
):
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            if not _is_read_timeout(exc):
                raise
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay_s = min(15.0, 5.0 * attempt)
            logfire.info(
                "BO API read timeout; retrying",
                operation=operation,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_s=delay_s,
                error=str(exc),
            )
            time.sleep(delay_s)
    assert last_exc is not None
    if continue_on_timeout:
        _record_runtime_warning(
            artifact_dir,
            operation=operation,
            message="Optional BO API call timed out; continuing without this step.",
            error=last_exc,
        )
        logfire.info(
            "Optional BO API call timed out; continuing without this step",
            operation=operation,
            error=str(last_exc),
        )
        return None
    raise last_exc


def _record_diagnostics(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> dict[str, Any] | None:
    diagnostics = _call_with_timeout_retries(
        "get_diagnostics",
        lambda: client.get_diagnostics(campaign_id, verbosity="standard"),
        artifact_dir=artifact_dir,
        continue_on_timeout=True,
    )
    if diagnostics is None:
        return None
    append_jsonl(artifact_dir / "diagnostics_history.jsonl", diagnostics)
    return diagnostics


def _current_campaign_candidate_ids(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> set[str]:
    export_result = _call_with_timeout_retries(
        "export_campaign_current",
        lambda: client.export_campaign(campaign_id, fmt="csv"),
        artifact_dir=artifact_dir,
    )
    content, content_type = export_result
    export_path = write_export(artifact_dir / "campaign_export_current", content, content_type)
    write_json(
        artifact_dir / "campaign_export_current_meta.json",
        {"content_type": content_type, "path": str(export_path)},
    )
    return existing_campaign_candidate_ids_from_export(content, content_type)


def _import_legacy_results_if_needed(prepared, client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> set[str]:
    existing_candidate_ids = _current_campaign_candidate_ids(client, campaign_id, artifact_dir)
    if prepared.config.skip_legacy_import:
        write_json(
            artifact_dir / "legacy_import_runtime.json",
            {
                "skipped": True,
                "reason": "skip_legacy_import flag set",
                "existing_candidate_count": len(existing_candidate_ids),
            },
        )
        return existing_candidate_ids

    pending_rows = [row for row in prepared.legacy_import_rows if row["candidate_id"] not in existing_candidate_ids]
    runtime_payload = {
        "skipped": False,
        "planned_count": len(prepared.legacy_import_rows),
        "already_present_count": len(prepared.legacy_import_rows) - len(pending_rows),
        "to_submit_count": len(pending_rows),
        "campaign_id": campaign_id,
    }
    write_json(artifact_dir / "legacy_import_runtime.json", runtime_payload)
    if not pending_rows:
        return existing_candidate_ids

    for row in pending_rows:
        submit_row = {key: value for key, value in row.items() if key != "candidate_id"}
        response = client.submit_results(
            campaign_id,
            results=[submit_row],
            idempotency_key=client.make_idempotency_key(
                "legacy-import",
                campaign_id,
                row["candidate_id"],
                prepared.config.run_label or "run",
            ),
        )
        append_jsonl(
            artifact_dir / "legacy_import_submissions.jsonl",
            {"candidate_id": row["candidate_id"], "response": response},
        )
        existing_candidate_ids.add(row["candidate_id"])
    return existing_candidate_ids


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
    campaign = _call_with_timeout_retries(
        "get_campaign_on_exit",
        lambda: client.get_campaign(campaign_id),
        artifact_dir=artifact_dir,
        continue_on_timeout=True,
    )
    status = ""
    if campaign is not None:
        write_json(artifact_dir / "final_campaign_state.json", campaign)
        status = str(campaign.get("status", "")).lower()
    action = "terminate" if terminate_on_exit else "pause"
    if action == "pause" and status and status != "running":
        return
    try:
        response = _call_with_timeout_retries(
            f"lifecycle_{action}",
            lambda: client.lifecycle(campaign_id, action=action),
            artifact_dir=artifact_dir,
            continue_on_timeout=True,
        )
    except (BoMcpClientError, BoMcpOperationError) as exc:
        _record_runtime_warning(
            artifact_dir,
            operation=f"lifecycle_{action}",
            message="Best-effort lifecycle action failed during shutdown cleanup.",
            error=exc,
        )
        logfire.info(
            "Best-effort lifecycle action failed during shutdown cleanup",
            operation=f"lifecycle_{action}",
            error=str(exc),
        )
        return
    if response is not None:
        write_json(artifact_dir / "lifecycle_on_exit.json", response)


def _run_execute_mode(prepared, intake: dict[str, Any], intake_backend: str) -> int:
    config = prepared.config
    artifact_dir = ensure_dir(config.artifact_dir)
    client, campaign_id = _create_or_attach_campaign(prepared, intake, artifact_dir)
    write_json(
        artifact_dir / "campaign_runtime.json",
        {
            "campaign_id": campaign_id,
            "intake_backend": intake_backend,
            "max_new_bo_successes": config.max_new_bo_successes,
        },
    )

    started = time.time()
    seen_candidates = _import_legacy_results_if_needed(prepared, client, campaign_id, artifact_dir)
    new_successes = 0

    while new_successes < config.max_new_bo_successes:
        elapsed_minutes = (time.time() - started) / 60.0
        if elapsed_minutes >= config.max_runtime_minutes:
            logfire.info("Stopping because invocation wall-clock budget was reached", elapsed_minutes=elapsed_minutes)
            break
        diagnostics = _record_diagnostics(client, campaign_id, artifact_dir)
        if diagnostics is None:
            logfire.info(
                "Campaign diagnostics unavailable after BO API timeout",
                campaign_id=campaign_id,
                new_successes=new_successes,
            )
        else:
            logfire.info(
                "Campaign diagnostics",
                campaign_id=campaign_id,
                n_results=diagnostics.get("n_results"),
                n_pending_suggestions=diagnostics.get("n_pending_suggestions"),
                iteration=diagnostics.get("iteration"),
                new_successes=new_successes,
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
                        "failure_reason": "Candidate already present in imported or previously submitted campaign results",
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
                new_successes += 1
                seen_candidates.add(candidate["candidate_id"])
                if new_successes >= config.max_new_bo_successes:
                    break
            else:
                client.update_suggestion_status(suggestion_id, "rejected")
                append_jsonl(artifact_dir / "results_failures.jsonl", result_to_jsonable(result))

    export_result = _call_with_timeout_retries(
        "export_campaign_final",
        lambda: client.export_campaign(campaign_id, fmt=config.export_format),
        artifact_dir=artifact_dir,
        continue_on_timeout=True,
    )
    if export_result is not None:
        content, content_type = export_result
        export_path = write_export(artifact_dir / "campaign_export", content, content_type)
        write_json(artifact_dir / "campaign_export_meta.json", {"content_type": content_type, "path": str(export_path)})
    _pause_or_terminate(client, campaign_id, config.terminate_on_exit, artifact_dir)
    print(f"Execution finished for campaign {campaign_id}. New BO successes this invocation: {new_successes}. Artifacts: {artifact_dir}")
    return 0


def main(config: Stage1bConfig) -> int:
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
        print("Preview-only mode: campaign creation, legacy import, and BO execution were skipped.")
        return 0
    return _run_execute_mode(prepared, validated_intake, intake_backend)


def cli_main(argv: list[str] | None = None) -> int:
    from .run_args import parse_args

    args = parse_args(argv)
    config = Stage1bConfig(**args)
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
