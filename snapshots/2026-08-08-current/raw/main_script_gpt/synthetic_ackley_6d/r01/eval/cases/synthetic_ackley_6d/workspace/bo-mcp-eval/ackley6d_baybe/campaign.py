from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import logfire
from grafico.core.logfire_config import configure_logfire

from domains.bo_mcp.client import BoMcpClient

from .objective import OBJECTIVE_NAME, OBJECTIVE_UNIT, PARAMETER_NAMES, ackley_surface, parameter_key

configure_logfire()
logfire.instrument_requests()

CAMPAIGN_MARKER = "akg-eval-3d7b8e82193946e0a546da000f3df95f"
CACHE_BUSTER_NONCE = "3982355b-d34f-496d-86f3-27ce76f1d4b9"
DEFAULT_RANDOM_SEED = 271828
DEFAULT_BATCH_SIZE = 5
DEFAULT_INITIAL_DESIGN_SIZE = 15
DEFAULT_ACQUISITION_METHOD = "expected_improvement"
TOTAL_EVALUATION_BUDGET = 60


@dataclass(frozen=True)
class CampaignConfig:
    campaign_name: str
    backend: str = "baybe"
    random_seed: int = DEFAULT_RANDOM_SEED
    batch_size: int = DEFAULT_BATCH_SIZE
    initial_design_size: int = DEFAULT_INITIAL_DESIGN_SIZE
    acquisition_method: str = DEFAULT_ACQUISITION_METHOD
    max_observations: int = TOTAL_EVALUATION_BUDGET
    total_budget: int = TOTAL_EVALUATION_BUDGET


class ArtifactWriter:
    def __init__(self, artifact_dir: Path) -> None:
        self.artifact_dir = artifact_dir
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.artifact_dir / "evaluations.jsonl"
        self.csv_path = self.artifact_dir / "evaluations.csv"
        self.summary_path = self.artifact_dir / "summary.json"
        self._csv_file = self.csv_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=[
                "evaluation_index",
                *PARAMETER_NAMES,
                OBJECTIVE_NAME,
                "raw_response",
                "status",
                "failure_reason",
                "suggestion_id",
            ],
        )
        self._csv_writer.writeheader()
        self.rows: list[dict[str, Any]] = []

    def record(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        flat = {
            "evaluation_index": row["evaluation_index"],
            "status": row["status"],
            "failure_reason": row.get("failure_reason") or "",
            "raw_response": row.get("raw_response", ""),
            OBJECTIVE_NAME: (row.get("objective_values") or {}).get(OBJECTIVE_NAME, ""),
            "suggestion_id": row.get("suggestion_id", ""),
        }
        for name in PARAMETER_NAMES:
            flat[name] = (row.get("parameter_values") or {}).get(name, "")
        self._csv_writer.writerow(flat)
        self._csv_file.flush()

    def write_summary(self, summary: dict[str, Any]) -> None:
        self.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    def close(self) -> None:
        self._csv_file.close()


class AckleyCampaignRunner:
    def __init__(
        self,
        *,
        artifact_root: Path,
        campaign_id: str | None = None,
        config: CampaignConfig | None = None,
    ) -> None:
        self.config = config or CampaignConfig(
            campaign_name=(
                f"ackley-6d-baybe-{CAMPAIGN_MARKER}-seed-{DEFAULT_RANDOM_SEED}-"
                f"nonce-{CACHE_BUSTER_NONCE[:8]}"
            )
        )
        self.client = BoMcpClient.from_env(timeout_s=120.0)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.artifact_dir = artifact_root / f"ackley6d_baybe_{timestamp}"
        self.writer = ArtifactWriter(self.artifact_dir)
        self.campaign_id = campaign_id
        self.seen_parameter_keys: set[tuple[str, ...]] = set()
        self.initial_server_results: list[dict[str, Any]] = []

    def build_intake(self) -> dict[str, Any]:
        return {
            "name": self.config.campaign_name,
            "description": (
                "Synthetic Ackley 6D benchmark with deterministic local evaluation. "
                f"Marker={CAMPAIGN_MARKER}. Nonce={CACHE_BUSTER_NONCE}."
            ),
            "backend": self.config.backend,
            "batch_size": self.config.batch_size,
            "initial_design_size": self.config.initial_design_size,
            "max_observations": self.config.max_observations,
            "random_seed": self.config.random_seed,
            "acquisition_method": self.config.acquisition_method,
            "parameters": [
                {
                    "name": name,
                    "type": "continuous",
                    "bounds": {"lower": 0.0, "upper": 1.0},
                    "description": f"Normalized Ackley coordinate {name}",
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

    def validate_only(self) -> dict[str, Any]:
        intake = self.build_intake()
        response = self.client.validate_intake(intake)
        manifest = {
            "package_modules": [
                "ackley6d_baybe.__init__",
                "ackley6d_baybe.objective",
                "ackley6d_baybe.campaign",
            ],
            "run_entrypoint": "run_ackley6d_baybe.py",
            "latest_artifact_dir": str(self.artifact_dir),
            "smoke_test": True,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
        Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.writer.write_summary({"mode": "smoke_test", "intake_validation": response})
        return response

    def ensure_campaign(self) -> str:
        if self.campaign_id:
            campaign = self.client.get_campaign(self.campaign_id)
            if CAMPAIGN_MARKER not in campaign["name"]:
                raise ValueError(
                    f"Refusing to use campaign {self.campaign_id}: missing ownership marker {CAMPAIGN_MARKER}."
                )
            status = (campaign.get("status") or "").lower()
            if status == "paused":
                self.client.lifecycle(self.campaign_id, action="resume")
            elif status == "completed":
                self.client.lifecycle(self.campaign_id, action="reopen")
            return self.campaign_id

        intake = self.build_intake()
        validation = self.client.validate_intake(intake)
        if not validation.get("valid", validation.get("success", True)):
            raise RuntimeError(f"Intake validation failed: {validation}")
        create_key = self.client.make_idempotency_key("create", self.config.campaign_name, CACHE_BUSTER_NONCE)
        created = self.client.create_campaign(intake, idempotency_key=create_key)
        self.campaign_id = created["campaign_id"]
        return self.campaign_id

    def _load_seen_from_server(self) -> list[dict[str, Any]]:
        assert self.campaign_id is not None
        results = self.client.get_results(self.campaign_id)
        self.seen_parameter_keys = set()
        for result in results:
            self.seen_parameter_keys.add(parameter_key(result.get("parameter_values") or {}))
        self.initial_server_results = results
        return results

    def _reject_duplicate_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        batch_seen: set[tuple[str, ...]] = set()
        for suggestion in suggestions:
            params = suggestion["parameter_values"]
            key = parameter_key(params)
            if key in self.seen_parameter_keys or key in batch_seen:
                self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                logfire.info("Rejected duplicate suggestion", suggestion_id=suggestion["suggestion_id"])
                continue
            batch_seen.add(key)
            accepted.append(suggestion)
        return accepted

    def _gather_unique_suggestions(self, needed: int) -> list[dict[str, Any]]:
        assert self.campaign_id is not None
        collected: list[dict[str, Any]] = []
        collected_keys: set[tuple[str, ...]] = set()
        attempts = 0
        while len(collected) < needed:
            attempts += 1
            pending = self.client.query_suggestions(self.campaign_id, status_filter="pending", limit=500)
            if pending:
                unique_pending = self._reject_duplicate_suggestions(pending)
                for suggestion in unique_pending:
                    key = parameter_key(suggestion["parameter_values"])
                    if key not in collected_keys:
                        collected.append(suggestion)
                        collected_keys.add(key)
                        if len(collected) == needed:
                            return collected
            generation = self.client.generate_suggestions(
                self.campaign_id,
                batch_size=max(1, needed - len(collected)),
                timeout_s=900.0,
            )
            fresh = self._reject_duplicate_suggestions(generation.get("suggestions") or [])
            for suggestion in fresh:
                key = parameter_key(suggestion["parameter_values"])
                if key not in collected_keys:
                    collected.append(suggestion)
                    collected_keys.add(key)
                    if len(collected) == needed:
                        return collected
            if attempts >= 10 and not fresh and not pending:
                raise RuntimeError("Unable to obtain enough unique suggestions within retry limit.")
        return collected

    def _record_success(self, evaluation_index: int, suggestion: dict[str, Any], evaluation: Any) -> dict[str, Any]:
        row = {
            "evaluation_index": evaluation_index,
            "parameter_values": evaluation.parameter_values,
            "objective_values": {OBJECTIVE_NAME: evaluation.surface_response},
            "status": "succeeded",
            "failure_reason": None,
            "raw_response": evaluation.raw_response,
            "suggestion_id": suggestion["suggestion_id"],
        }
        self.writer.record(row)
        self.seen_parameter_keys.add(parameter_key(evaluation.parameter_values))
        return row

    def _server_results_as_rows(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for idx, result in enumerate(results, start=1):
            evaluation = ackley_surface(result["parameter_values"])
            rows.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": evaluation.parameter_values,
                    "objective_values": {OBJECTIVE_NAME: evaluation.surface_response},
                    "status": "succeeded",
                    "failure_reason": None,
                    "raw_response": evaluation.raw_response,
                    "suggestion_id": result.get("suggestion_id"),
                }
            )
        return rows

    def run(self) -> dict[str, Any]:
        campaign_id = self.ensure_campaign()
        existing_results = self._load_seen_from_server()
        attempted = len(existing_results)
        successful = len(existing_results)
        logfire.info("Starting Ackley optimization run", campaign_id=campaign_id, existing_results=attempted)

        while attempted < self.config.total_budget:
            decision = self.client.next_action(campaign_id)
            if decision.get("action") != "bo_generate_suggestions":
                break
            remaining = self.config.total_budget - attempted
            target_batch = min(self.config.batch_size, remaining)
            suggestions = self._gather_unique_suggestions(target_batch)
            if not suggestions:
                break

            result_payload: list[dict[str, Any]] = []
            batch_suggestion_ids: list[str] = []
            for suggestion in suggestions:
                attempted += 1
                try:
                    evaluation = ackley_surface(suggestion["parameter_values"])
                    row = self._record_success(attempted, suggestion, evaluation)
                    successful += 1
                    batch_suggestion_ids.append(suggestion["suggestion_id"])
                    result_payload.append(
                        {
                            "suggestion_id": suggestion["suggestion_id"],
                            "parameter_values": row["parameter_values"],
                            "objective_values": row["objective_values"],
                            "metadata": {
                                "notes": "Deterministic local Ackley 6D synthetic benchmark",
                                "experiment_id": f"ackley6d-eval-{attempted}",
                            },
                        }
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    failed_row = {
                        "evaluation_index": attempted,
                        "parameter_values": suggestion["parameter_values"],
                        "objective_values": None,
                        "status": "failed",
                        "failure_reason": str(exc),
                        "raw_response": None,
                        "suggestion_id": suggestion["suggestion_id"],
                    }
                    self.writer.record(failed_row)
                    self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")

            if result_payload:
                submit_key = self.client.make_idempotency_key(
                    "submit",
                    campaign_id,
                    *sorted(batch_suggestion_ids),
                )
                self.client.submit_results(
                    campaign_id,
                    results=result_payload,
                    idempotency_key=submit_key,
                    force=False,
                )

        diagnostics = self.client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=900.0)
        campaign = self.client.get_campaign(campaign_id)
        status = (campaign.get("status") or "").lower()
        if status in {"created", "running"}:
            self.client.lifecycle(campaign_id, action="pause")
            status = "paused"
        export_bytes, export_mime = self.client.export_campaign(campaign_id, fmt="csv")
        export_path = self.artifact_dir / "bo_mcp_export.csv"
        export_path.write_bytes(export_bytes)

        final_server_results = self.client.get_results(campaign_id)
        all_rows = self._server_results_as_rows(final_server_results)
        if len(all_rows) < len(self.writer.rows):
            all_rows.extend(self.writer.rows[len(all_rows):])
        best_row = max(all_rows, key=lambda row: row["objective_values"][OBJECTIVE_NAME]) if all_rows else None
        summary = {
            "campaign_id": campaign_id,
            "campaign_status": status,
            "backend": self.config.backend,
            "attempted_evaluations": len(all_rows),
            "successful_evaluations": sum(1 for row in all_rows if row["status"] == "succeeded"),
            "objective_name": OBJECTIVE_NAME,
            "objective_unit": OBJECTIVE_UNIT,
            "best_result": best_row,
            "artifacts": {
                "evaluation_jsonl": str(self.writer.jsonl_path),
                "evaluation_csv": str(self.writer.csv_path),
                "export_csv": str(export_path),
                "export_mime": export_mime,
            },
            "all_rows": all_rows,
            "diagnostics": diagnostics,
        }
        self.writer.write_summary(summary)
        manifest = {
            "package_modules": [
                "ackley6d_baybe.__init__",
                "ackley6d_baybe.objective",
                "ackley6d_baybe.campaign",
            ],
            "run_entrypoint": "run_ackley6d_baybe.py",
            "latest_artifact_dir": str(self.artifact_dir),
            "campaign_id": campaign_id,
            "campaign_name": self.config.campaign_name,
            "ownership_marker": CAMPAIGN_MARKER,
            "cache_buster_nonce": CACHE_BUSTER_NONCE,
        }
        Path("campaign_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return summary

    def close(self) -> None:
        self.writer.close()
