from __future__ import annotations

import csv
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import logfire
from grafico.core.logfire_config import configure_logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .ackley import OBJECTIVE_NAME, OBJECTIVE_UNIT, PARAMETER_NAMES, evaluate_ackley, parameter_key

configure_logfire()
logfire.instrument_requests()

MARKER = "akg-eval-e4b7bf86febf4353a5becc32d3e1173e"
DEFAULT_BACKEND = "botorch"
DEFAULT_BATCH_SIZE = 6
DEFAULT_INITIAL_DESIGN_SIZE = 12
DEFAULT_ACQUISITION_METHOD = "expected_improvement"
DEFAULT_RANDOM_SEED = 2132743523


@dataclass(frozen=True)
class CampaignSettings:
    campaign_name: str
    description: str
    backend: str = DEFAULT_BACKEND
    batch_size: int = DEFAULT_BATCH_SIZE
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE
    acquisition_method: str = DEFAULT_ACQUISITION_METHOD
    random_seed: int = DEFAULT_RANDOM_SEED
    target_attempted_evaluations: int = 60


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_intake(settings: CampaignSettings) -> dict[str, Any]:
    return {
        "name": settings.campaign_name,
        "description": settings.description,
        "backend": settings.backend,
        "batch_size": settings.batch_size,
        "initial_design_size": settings.initial_design_size,
        "random_seed": settings.random_seed,
        "acquisition_method": settings.acquisition_method,
        "parameters": [
            {
                "name": name,
                "type": "continuous",
                "bounds": {"lower": 0.0, "upper": 1.0},
                "description": f"Normalized Ackley dimension {name}",
            }
            for name in PARAMETER_NAMES
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


class AckleyBenchmarkRunner:
    def __init__(self, *, workspace: Path, artifact_root: Path, settings: CampaignSettings):
        self.workspace = workspace
        self.artifact_root = artifact_root
        self.settings = settings
        self.client = BoMcpClient.from_env(timeout_s=120.0)
        self.evaluated_keys: set[tuple[str, ...]] = set()
        self.attempted_evaluations = 0
        self.successful_evaluations = 0
        self.records: list[dict[str, Any]] = []
        self.campaign_id: str | None = None
        self.artifact_dir: Path | None = None
        self.jsonl_path: Path | None = None
        self.csv_path: Path | None = None
        self.report_path: Path | None = None
        self.summary_path: Path | None = None
        self.diagnostics_path: Path | None = None

    def ensure_campaign(self, campaign_id: str | None) -> str:
        if campaign_id:
            campaign = self.client.get_campaign(campaign_id)
            name = (campaign.get("name") or campaign.get("campaign", {}).get("name") or "")
            if MARKER not in name:
                raise RuntimeError(f"Refusing to resume campaign without ownership marker: {campaign_id}")
            status = str(campaign.get("status") or campaign.get("campaign", {}).get("status") or "").upper()
            logfire.info("Resuming existing campaign", campaign_id=campaign_id, status=status)
            if status == "PAUSED":
                self.client.lifecycle(campaign_id, action="resume")
            elif status == "COMPLETED":
                self.client.lifecycle(campaign_id, action="reopen")
            elif status in {"CREATED", "RUNNING"}:
                pass
            else:
                raise RuntimeError(f"Campaign {campaign_id} is not resumable from status {status}")
            self.campaign_id = campaign_id
            return campaign_id

        intake = build_intake(self.settings)
        validation = self.client.validate_intake(intake)
        if not validation.get("valid"):
            raise RuntimeError(f"Intake validation failed: {validation}")
        logfire.info("Validated campaign intake", validation=validation)
        response = self.client.create_campaign(intake, idempotency_key=str(uuid.uuid4()))
        created_id = response["campaign_id"]
        self.campaign_id = created_id
        logfire.info("Created campaign", campaign_id=created_id, response=response)
        return created_id

    def prepare_artifacts(self, campaign_id: str) -> None:
        self.artifact_dir = self.artifact_root / f"ackley_surface_6d__{utc_timestamp()}__{campaign_id}"
        self.artifact_dir.mkdir(parents=True, exist_ok=False)
        self.jsonl_path = self.artifact_dir / "evaluations.jsonl"
        self.csv_path = self.artifact_dir / "evaluations.csv"
        self.report_path = self.artifact_dir / "final_report.md"
        self.summary_path = self.artifact_dir / "summary.json"
        self.diagnostics_path = self.artifact_dir / "diagnostics.json"
        self._write_manifest(self.artifact_dir)

    def _write_manifest(self, latest_artifact_dir: Path) -> None:
        manifest = {
            "package_modules": [
                "ackley_surface_6d.__init__",
                "ackley_surface_6d.ackley",
                "ackley_surface_6d.campaign",
            ],
            "run_entrypoint": "run_ackley_surface_6d.py",
            "latest_artifact_dir": str(latest_artifact_dir),
        }
        (self.workspace / "campaign_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def load_existing_results(self, campaign_id: str) -> None:
        existing_results = self.client.get_results(campaign_id)
        self.evaluated_keys = {parameter_key(row["parameter_values"]) for row in existing_results}
        self.attempted_evaluations = len(existing_results)
        self.successful_evaluations = len(existing_results)
        logfire.info(
            "Loaded existing BO-MCP results",
            campaign_id=campaign_id,
            existing_results=len(existing_results),
        )

    def remaining_budget(self) -> int:
        return self.settings.target_attempted_evaluations - self.attempted_evaluations

    def run(self) -> dict[str, Any]:
        assert self.campaign_id is not None
        assert self.artifact_dir is not None
        assert self.jsonl_path is not None
        campaign_id = self.campaign_id
        while self.remaining_budget() > 0:
            decision = self.client.next_action(campaign_id)
            logfire.info("Server next_action", campaign_id=campaign_id, decision=decision)
            if decision.get("action") != "bo_generate_suggestions":
                raise RuntimeError(
                    f"Server declined further suggestion generation before budget exhaustion: {decision}"
                )
            suggestions = self._acquire_novel_suggestions(campaign_id, desired_count=min(self.settings.batch_size, self.remaining_budget()))
            if not suggestions:
                raise RuntimeError("No novel suggestions available before exhausting the benchmark budget")
            submission_rows: list[dict[str, Any]] = []
            for suggestion in suggestions:
                parameter_values = {name: float(suggestion["parameter_values"][name]) for name in PARAMETER_NAMES}
                key = parameter_key(parameter_values)
                if key in self.evaluated_keys:
                    raise RuntimeError("Duplicate suggestion survived filtering; aborting to honor benchmark contract")
                self.attempted_evaluations += 1
                evaluation_index = self.attempted_evaluations
                try:
                    evaluation = evaluate_ackley(parameter_values)
                    record = {
                        "evaluation_index": evaluation_index,
                        "campaign_id": campaign_id,
                        "suggestion_id": suggestion["suggestion_id"],
                        "parameter_values": parameter_values,
                        "objective_values": {OBJECTIVE_NAME: evaluation[OBJECTIVE_NAME]},
                        "status": "success",
                        "failure_reason": None,
                        "raw_response": evaluation["raw_response"],
                    }
                    self._append_record(record)
                    self.evaluated_keys.add(key)
                    self.successful_evaluations += 1
                    submission_rows.append(
                        {
                            "parameter_values": parameter_values,
                            "objective_values": {OBJECTIVE_NAME: evaluation[OBJECTIVE_NAME]},
                            "suggestion_id": suggestion["suggestion_id"],
                            "metadata": {
                                "batch_ref": f"ackley-6d-{campaign_id}",
                                "experiment_id": f"ackley-eval-{evaluation_index}",
                                "notes": f"raw_response={evaluation['raw_response']:.15f}",
                            },
                        }
                    )
                except Exception as exc:  # pragma: no cover - defensive path for benchmark robustness
                    record = {
                        "evaluation_index": evaluation_index,
                        "campaign_id": campaign_id,
                        "suggestion_id": suggestion["suggestion_id"],
                        "parameter_values": parameter_values,
                        "objective_values": {},
                        "status": "failed",
                        "failure_reason": str(exc),
                        "raw_response": None,
                    }
                    self._append_record(record)
                    self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
            if submission_rows:
                response = self.client.submit_results(
                    campaign_id,
                    results=submission_rows,
                    idempotency_key=str(uuid.uuid4()),
                    force=False,
                )
                logfire.info("Submitted result batch", campaign_id=campaign_id, submitted=len(submission_rows), response=response)

        diagnostics = self.client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=600.0)
        self.diagnostics_path.write_text(json.dumps(diagnostics, indent=2) + "\n")
        campaign = self.client.get_campaign(campaign_id)
        status = str(campaign.get("status") or campaign.get("campaign", {}).get("status") or "").upper()
        if status in {"RUNNING", "CREATED"}:
            self.client.lifecycle(campaign_id, action="pause")
            status = "PAUSED"
        summary = self._build_summary(campaign_id=campaign_id, final_status=status, diagnostics=diagnostics)
        self._write_outputs(summary)
        return summary

    def _acquire_novel_suggestions(self, campaign_id: str, desired_count: int) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        seen_batch_keys: set[tuple[str, ...]] = set()

        def consider(suggestion: dict[str, Any]) -> None:
            key = parameter_key(suggestion["parameter_values"])
            if key in self.evaluated_keys or key in seen_batch_keys:
                logfire.info("Rejecting duplicate suggestion to honor benchmark contract", suggestion_id=suggestion["suggestion_id"], parameter_key=key)
                self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                return
            seen_batch_keys.add(key)
            collected.append(suggestion)

        pending = self.client.query_suggestions(campaign_id, status_filter="pending", limit=500)
        for suggestion in pending:
            if len(collected) >= desired_count:
                break
            consider(suggestion)

        generation_attempts = 0
        while len(collected) < desired_count:
            generation_attempts += 1
            if generation_attempts > 12:
                raise RuntimeError("Exceeded suggestion-generation retries while seeking novel points")
            needed = desired_count - len(collected)
            generated = self.client.generate_suggestions(campaign_id, batch_size=needed, timeout_s=900.0)
            if not generated.get("success"):
                raise RuntimeError(f"Suggestion generation failed: {generated}")
            for suggestion in generated.get("suggestions", []):
                if len(collected) >= desired_count:
                    break
                consider(suggestion)
            if not generated.get("suggestions") and len(collected) < desired_count:
                raise RuntimeError(f"No suggestions produced while {needed} novel points were still needed")
        return collected

    def _append_record(self, record: dict[str, Any]) -> None:
        assert self.jsonl_path is not None
        self.records.append(record)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    def _build_summary(self, *, campaign_id: str, final_status: str, diagnostics: dict[str, Any]) -> dict[str, Any]:
        success_records = [row for row in self.records if row["status"] == "success"]
        if success_records:
            best_record = max(success_records, key=lambda row: row["objective_values"][OBJECTIVE_NAME])
        else:
            best_record = None
        return {
            "campaign_id": campaign_id,
            "campaign_name": self.settings.campaign_name,
            "campaign_marker": MARKER,
            "objective_name": OBJECTIVE_NAME,
            "objective_direction": "maximize",
            "objective_unit": OBJECTIVE_UNIT,
            "backend": self.settings.backend,
            "batch_size": self.settings.batch_size,
            "initial_design_size": self.settings.initial_design_size,
            "acquisition_method": self.settings.acquisition_method,
            "random_seed": self.settings.random_seed,
            "attempted_evaluations": self.attempted_evaluations,
            "successful_evaluations": self.successful_evaluations,
            "failed_evaluations": self.attempted_evaluations - self.successful_evaluations,
            "best_record": best_record,
            "records": self.records,
            "final_status": final_status,
            "diagnostics": diagnostics,
        }

    def _write_outputs(self, summary: dict[str, Any]) -> None:
        assert self.csv_path is not None
        assert self.report_path is not None
        assert self.summary_path is not None
        rows = []
        for record in self.records:
            row = {
                "evaluation_index": record["evaluation_index"],
                **{name: record["parameter_values"].get(name) for name in PARAMETER_NAMES},
                OBJECTIVE_NAME: record["objective_values"].get(OBJECTIVE_NAME),
                "status": record["status"],
                "failure_reason": record["failure_reason"],
                "raw_response": record["raw_response"],
                "suggestion_id": record.get("suggestion_id"),
                "campaign_id": record.get("campaign_id"),
            }
            rows.append(row)
        with self.csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "evaluation_index",
                    *PARAMETER_NAMES,
                    OBJECTIVE_NAME,
                    "status",
                    "failure_reason",
                    "raw_response",
                    "suggestion_id",
                    "campaign_id",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        self.summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        self.report_path.write_text(self._render_report(summary), encoding="utf-8")

    def _render_report(self, summary: dict[str, Any]) -> str:
        lines = [
            f"# Ackley 6D Benchmark Report\n",
            f"- campaign_id: {summary['campaign_id']}",
            f"- campaign_name: {summary['campaign_name']}",
            f"- attempted_evaluations: {summary['attempted_evaluations']}",
            f"- successful_evaluations: {summary['successful_evaluations']}",
            f"- final_status: {summary['final_status']}",
            "",
        ]
        best_record = summary.get("best_record")
        if best_record:
            lines.extend(
                [
                    "## Best Record",
                    f"- evaluation_index: {best_record['evaluation_index']}",
                    f"- raw_response: {best_record['raw_response']}",
                    f"- {OBJECTIVE_NAME}: {best_record['objective_values'][OBJECTIVE_NAME]}",
                    f"- parameter_values: {json.dumps(best_record['parameter_values'], sort_keys=True)}",
                    "",
                ]
            )
        lines.append("## Evaluations")
        lines.append("")
        lines.append(f"| evaluation_index | {' | '.join(PARAMETER_NAMES)} | {OBJECTIVE_NAME} | status | raw_response |")
        lines.append(f"| --- | {' | '.join(['---'] * len(PARAMETER_NAMES))} | --- | --- | --- |")
        for record in summary["records"]:
            params = [f"{record['parameter_values'][name]:.8f}" for name in PARAMETER_NAMES]
            objective_value = record["objective_values"].get(OBJECTIVE_NAME)
            objective_text = "" if objective_value is None else f"{objective_value:.8f}"
            raw_text = "" if record["raw_response"] is None else f"{record['raw_response']:.8f}"
            lines.append(
                f"| {record['evaluation_index']} | {' | '.join(params)} | {objective_text} | {record['status']} | {raw_text} |"
            )
        lines.append("")
        return "\n".join(lines)


def build_settings(*, evaluation_budget: int, smoke_test: bool) -> CampaignSettings:
    timestamp = utc_timestamp()
    name_prefix = "smoke" if smoke_test else "prod"
    campaign_name = f"ackley-6d-{name_prefix}-{timestamp}-{MARKER}"
    description = (
        "Synthetic 6D Ackley benchmark with deterministic Python evaluator; "
        "maximize normalized surface_response in normalized_unitless."
    )
    return CampaignSettings(
        campaign_name=campaign_name,
        description=description,
        target_attempted_evaluations=evaluation_budget,
    )
