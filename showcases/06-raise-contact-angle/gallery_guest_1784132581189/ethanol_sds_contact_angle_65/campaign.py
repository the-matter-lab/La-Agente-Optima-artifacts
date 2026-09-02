from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .evaluator import EvaluationOutcome, evaluate_candidate, within_target_window
from .intake import build_intake
from .reporting import append_jsonl, ensure_artifact_dir, render_summary, summarize_results, write_json
from .search_space import CAMPAIGN_SLUG, MATCH_TOLERANCE_DEG, TARGET_ANGLE_DEG
from .seeding import DEFAULT_SEED_SOURCES, load_seed_results


@dataclass
class CampaignConfig:
    campaign_name: str
    campaign_description: str
    artifacts_root: Path = Path("artifacts")
    campaign_id: str | None = None
    manifest_path: Path = Path("campaign_manifest.json")
    random_seed: int = 7
    raise_timeout_s: int = 500
    target_angle_deg: float = TARGET_ANGLE_DEG
    tolerance_deg: float = MATCH_TOLERANCE_DEG
    bo_iteration_budget: int = 5
    measurement_retries: int = 2
    terminate_on_exit: bool = False


def run_campaign(config: CampaignConfig) -> dict[str, Any]:
    client = BoMcpClient.from_env(timeout_s=120)
    created_new = False

    if config.campaign_id:
        campaign_id = config.campaign_id
        campaign = client.get_campaign(campaign_id)
    else:
        intake = build_intake(
            name=config.campaign_name,
            description=config.campaign_description,
            random_seed=config.random_seed,
        )
        validation = client.validate_intake(intake)
        if not validation.get("valid"):
            raise RuntimeError(f"Campaign intake validation failed: {validation.get('errors')}")
        create_key = f"create-{CAMPAIGN_SLUG}-{uuid4().hex}"
        created = client.create_campaign(intake, idempotency_key=create_key)
        campaign_id = str(created["campaign_id"])
        campaign = client.get_campaign(campaign_id)
        created_new = True
        print(f"Created campaign {campaign_id}")
        logfire.info("Created campaign {campaign_id}", campaign_id=campaign_id)

    artifact_dir = ensure_artifact_dir(config.artifacts_root, CAMPAIGN_SLUG, campaign_id)
    evaluation_log_path = artifact_dir / "evaluations.jsonl"

    write_json(
        artifact_dir / "run_context.json",
        {
            "campaign_id": campaign_id,
            "campaign_name": campaign.get("name"),
            "created_new": created_new,
            "config": _json_ready_config(config),
        },
    )

    rows = _query_results(client, campaign_id)
    if not rows:
        seed_rows, seed_summary = load_seed_results(sources=DEFAULT_SEED_SOURCES)
        write_json(artifact_dir / "seed_filter_summary.json", seed_summary.to_dict())
        if seed_rows:
            print(f"Seeding {len(seed_rows)} unique historical results from prior campaigns")
            for source_summary in seed_summary.sources:
                print(
                    "  "
                    f"{source_summary.source_campaign_id}: "
                    f"seeded {source_summary.seeded_rows}/{source_summary.valid_rows} valid rows, "
                    f"excluded {source_summary.excluded_rows}, "
                    f"duplicates {source_summary.duplicate_rows}"
                )
            submit_response = client.submit_results(
                campaign_id,
                results=seed_rows,
                idempotency_key=f"seed-{campaign_id}-{uuid4().hex}",
            )
            write_json(
                artifact_dir / "seed_upload.json",
                {
                    "seeded_result_count": len(seed_rows),
                    "seed_summary": seed_summary.to_dict(),
                    "submit_response": submit_response,
                },
            )
            logfire.info(
                "Seeded historical results for campaign {campaign_id}",
                campaign_id=campaign_id,
                seeded_result_count=len(seed_rows),
            )
        else:
            print("No valid historical results were found to seed.")
        rows = _query_results(client, campaign_id)
    else:
        print(f"Existing campaign already has {len(rows)} results; skipping seed upload.")

    summary = summarize_results(
        rows,
        target=config.target_angle_deg,
        tolerance=config.tolerance_deg,
    )
    print(
        f"Starting state: {render_summary(summary, target=config.target_angle_deg, tolerance=config.tolerance_deg)}"
    )

    stop_reason: str | None = None
    if summary["within_tolerance"]:
        stop_reason = "Existing seeded or resumed results already satisfy the ±1° target window."
    elif config.bo_iteration_budget <= 0:
        stop_reason = "No BO iterations requested for this invocation."
    else:
        _ensure_mutable_campaign_state(client, campaign_id, campaign.get("status"))
        executed_bo = 0
        while executed_bo < config.bo_iteration_budget:
            decision = client.next_action(campaign_id)
            if decision.get("action") != "bo_generate_suggestions":
                stop_reason = (
                    "BO-MCP advised stopping before another BO iteration: "
                    f"{decision.get('action')} ({decision.get('reason')})"
                )
                break
            suggestion = _next_suggestion(client, campaign_id)
            candidate = {key: float(value) for key, value in suggestion["parameter_values"].items()}
            print(
                f"BO iteration {executed_bo + 1}/{config.bo_iteration_budget}: "
                f"suggestion {suggestion['id']} -> "
                f"Ethanol={candidate['Ethanol']:.6f}, SDS={candidate['SDS']:.6f}"
            )
            outcome, submit_response = _evaluate_and_submit(
                client=client,
                campaign_id=campaign_id,
                candidate=candidate,
                suggestion_id=str(suggestion["id"]),
                phase="bo",
                sequence_index=executed_bo + 1,
                timeout_s=config.raise_timeout_s,
                note="BO-suggested experiment",
                evaluation_log_path=evaluation_log_path,
                measurement_retries=config.measurement_retries,
            )
            executed_bo += 1
            rows = _query_results(client, campaign_id)
            summary = summarize_results(
                rows,
                target=config.target_angle_deg,
                tolerance=config.tolerance_deg,
            )
            if submit_response is not None:
                print(
                    f"  Submitted result {submit_response.get('result_ids', ['?'])[0]} | "
                    f"{render_summary(summary, target=config.target_angle_deg, tolerance=config.tolerance_deg)}"
                )
            else:
                print(
                    "  No BO result submitted | "
                    f"{render_summary(summary, target=config.target_angle_deg, tolerance=config.tolerance_deg)}"
                )
            if outcome.measured_angle is not None and within_target_window(
                outcome.measured_angle,
                target=config.target_angle_deg,
                tolerance=config.tolerance_deg,
            ):
                stop_reason = "BO result hit the ±1° target window."
                break
        if stop_reason is None:
            stop_reason = "Reached the requested BO-iteration budget for this invocation."

    diagnostics_payload = _best_effort_diagnostics(client, campaign_id)
    if diagnostics_payload is not None:
        write_json(artifact_dir / "diagnostics.json", diagnostics_payload)

    export_path = _best_effort_export(client, campaign_id, artifact_dir)
    cleanup = _finalize_campaign_state(client, campaign_id, terminate_on_exit=config.terminate_on_exit)
    final_campaign = client.get_campaign(campaign_id)

    final_rows = _query_results(client, campaign_id)
    final_summary = summarize_results(
        final_rows,
        target=config.target_angle_deg,
        tolerance=config.tolerance_deg,
    )
    write_json(
        artifact_dir / "run_summary.json",
        {
            "campaign_id": campaign_id,
            "stop_reason": stop_reason,
            "summary": final_summary,
            "final_campaign_status": final_campaign.get("status"),
            "cleanup": cleanup,
            "artifact_dir": str(artifact_dir),
            "export_path": str(export_path) if export_path else None,
        },
    )
    _write_manifest(config.manifest_path, artifact_dir)

    print(f"Stop reason: {stop_reason}")
    print(f"Artifacts: {artifact_dir}")
    return {
        "campaign_id": campaign_id,
        "artifact_dir": str(artifact_dir),
        "stop_reason": stop_reason,
        "summary": final_summary,
        "final_campaign_status": final_campaign.get("status"),
        "export_path": str(export_path) if export_path else None,
    }


def _json_ready_config(config: CampaignConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["artifacts_root"] = str(config.artifacts_root)
    payload["manifest_path"] = str(config.manifest_path)
    return payload


def _ensure_mutable_campaign_state(
    client: BoMcpClient,
    campaign_id: str,
    current_status: str | None,
) -> None:
    if current_status == "paused":
        client.lifecycle(campaign_id, action="resume")
        print(f"Resumed paused campaign {campaign_id}")
    elif current_status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        print(f"Reopened completed campaign {campaign_id}")


def _query_results(client: BoMcpClient, campaign_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    limit = 500
    while True:
        response = client._json_request(
            "POST",
            f"/api/v1/results/{campaign_id}/query",
            json={"limit": limit, "offset": offset, "verbosity": "detailed"},
        )
        batch = response.get("results") or []
        rows.extend(batch)
        if len(batch) < limit:
            return rows
        offset += limit


def _next_suggestion(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    pending = client.query_suggestions(campaign_id, status_filter="pending")
    if pending:
        pending_sorted = sorted(pending, key=lambda row: (row.get("created_at", ""), row.get("id", "")))
        print(f"Reusing pending suggestion {pending_sorted[0]['id']}")
        return pending_sorted[0]
    try:
        response = client.generate_suggestions(campaign_id, batch_size=1)
    except BoMcpOperationError as exc:
        errors = exc.payload.get("errors") or [str(exc)]
        raise RuntimeError(f"BO suggestion generation stopped: {errors}") from exc
    suggestions = response.get("suggestions") or []
    if not suggestions:
        raise RuntimeError("BO-MCP returned no suggestions.")
    return suggestions[0]


def _evaluate_and_submit(
    *,
    client: BoMcpClient,
    campaign_id: str,
    candidate: dict[str, float],
    suggestion_id: str | None,
    phase: str,
    sequence_index: int,
    timeout_s: int,
    note: str,
    evaluation_log_path: Path,
    measurement_retries: int,
) -> tuple[EvaluationOutcome, dict[str, Any] | None]:
    max_attempts = max(1, measurement_retries + 1)
    attempts: list[dict[str, Any]] = []
    final_outcome: EvaluationOutcome | None = None

    for attempt_index in range(1, max_attempts + 1):
        outcome = evaluate_candidate(candidate, timeout_s=timeout_s)
        attempts.append({"attempt_index": attempt_index, "evaluation": outcome.to_dict()})
        final_outcome = outcome
        if outcome.success:
            print(f"  Measured static contact angle = {outcome.measured_angle:.3f}°")
            break
        if outcome.retryable and attempt_index < max_attempts:
            print(
                f"  Measurement failure on attempt {attempt_index}/{max_attempts}: {outcome.error}"
            )
            print("  Retrying same candidate...")
            continue
        break

    assert final_outcome is not None
    log_payload = {
        "phase": phase,
        "sequence_index": sequence_index,
        "suggestion_id": suggestion_id,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "final_evaluation": final_outcome.to_dict(),
    }

    if final_outcome.success:
        result_row = {
            "parameter_values": final_outcome.candidate,
            "objective_values": {"static_contact_angle": final_outcome.submitted_angle},
            "metadata": {
                "experiment_id": f"{campaign_id}-{phase}-{sequence_index}",
                "notes": note,
                "conditions": {
                    "phase": phase,
                    "success": final_outcome.success,
                    "sequence_index": sequence_index,
                    "attempt_count": len(attempts),
                },
            },
        }
        if suggestion_id is not None:
            result_row["suggestion_id"] = suggestion_id
        submit_key = f"submit-{campaign_id}-{phase}-{sequence_index}-{suggestion_id or 'seed'}"
        submit_response = client.submit_results(
            campaign_id,
            results=[result_row],
            idempotency_key=submit_key,
        )
        log_payload["submit_response"] = submit_response
        append_jsonl(evaluation_log_path, log_payload)
        logfire.info(
            "Submitted {phase} result for campaign {campaign_id}",
            phase=phase,
            campaign_id=campaign_id,
            suggestion_id=suggestion_id,
            success=final_outcome.success,
            measured_angle=final_outcome.measured_angle,
            submitted_angle=final_outcome.submitted_angle,
            attempt_count=len(attempts),
        )
        return final_outcome, submit_response

    if final_outcome.retryable:
        status_response = None
        if suggestion_id is not None:
            status_response = client.update_suggestion_status(suggestion_id, "expired")
        print(
            "  Measurement failed after "
            f"{len(attempts)} attempt(s) -> suggestion marked expired; no BO result submitted."
        )
        log_payload["suggestion_status_update"] = status_response
        append_jsonl(evaluation_log_path, log_payload)
        logfire.info(
            "Expired suggestion after measurement failure for campaign {campaign_id}",
            campaign_id=campaign_id,
            suggestion_id=suggestion_id,
            attempt_count=len(attempts),
        )
        return final_outcome, None

    append_jsonl(evaluation_log_path, log_payload)
    raise RuntimeError(f"Candidate evaluation failed before BO submission: {final_outcome.error}")


def _best_effort_diagnostics(client: BoMcpClient, campaign_id: str) -> dict[str, Any] | None:
    try:
        print("Fetching diagnostics...")
        return client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=600)
    except Exception as exc:
        print(f"Diagnostics skipped: {exc}")
        return None


def _best_effort_export(
    client: BoMcpClient,
    campaign_id: str,
    artifact_dir: Path,
) -> Path | None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
    except Exception as exc:
        print(f"Export skipped: {exc}")
        return None
    suffix = ".csv" if "csv" in content_type.lower() else ".bin"
    export_path = artifact_dir / f"campaign_export{suffix}"
    export_path.write_bytes(content)
    return export_path


def _finalize_campaign_state(
    client: BoMcpClient,
    campaign_id: str,
    *,
    terminate_on_exit: bool,
) -> dict[str, Any] | None:
    campaign = client.get_campaign(campaign_id)
    status = campaign.get("status")
    if terminate_on_exit and status not in {"terminated"}:
        response = client.lifecycle(campaign_id, action="terminate")
        print(f"Terminated campaign {campaign_id}")
        return response
    if status == "running":
        response = client.lifecycle(campaign_id, action="pause")
        print(f"Paused campaign {campaign_id}")
        return response
    return None


def _write_manifest(manifest_path: Path, artifact_dir: Path) -> None:
    write_json(
        manifest_path,
        {
            "campaign_slug": CAMPAIGN_SLUG,
            "package_modules": [
                "ethanol_sds_contact_angle_65/__init__.py",
                "ethanol_sds_contact_angle_65/search_space.py",
                "ethanol_sds_contact_angle_65/intake.py",
                "ethanol_sds_contact_angle_65/evaluator.py",
                "ethanol_sds_contact_angle_65/reporting.py",
                "ethanol_sds_contact_angle_65/seeding.py",
                "ethanol_sds_contact_angle_65/campaign.py",
            ],
            "run_entrypoint": "continue_ethanol_sds_contact_angle_65.py",
            "latest_artifact_directory": str(artifact_dir),
        },
    )

