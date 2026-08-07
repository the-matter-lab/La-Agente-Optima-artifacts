from __future__ import annotations

import csv
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .ackley import PARAMETER_NAMES, evaluate_ackley_6d, point_key

MARKER = "akg-eval-aec7138fc7b443a08c3a021815ff43af"
NONCE = "c33313ce-be38-46b9-850c-838405edd7bf"
OBJECTIVE_NAME = "surface_response"
OBJECTIVE_DIRECTION = "maximize"
OBJECTIVE_UNIT = "normalized_unitless"


@dataclass(frozen=True)
class AckleyRunConfig:
    total_budget: int = 60
    default_batch_size: int = 4
    initial_design_size: int = 16
    acquisition_method: str = "noisy_expected_improvement"
    backend: str = "botorch"
    max_batches: int | None = None
    random_seed: int = int(uuid.UUID(NONCE)) % 2_147_483_647
    invocation_label: str = "production"


class AckleyCampaignRunner:
    def __init__(self, config: AckleyRunConfig, workspace: Path):
        self.config = config
        self.workspace = workspace
        self.client = BoMcpClient.from_env(timeout_s=120.0)

    @property
    def campaign_slug(self) -> str:
        return "ackley_synth_6d"

    def campaign_name(self) -> str:
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        return f"ackley-6d-{MARKER}-{timestamp}-{self.config.invocation_label}"

    def build_intake(self) -> dict[str, Any]:
        return {
            "name": self.campaign_name(),
            "description": (
                "Synthetic 6D Ackley surface benchmark with deterministic Python evaluation. "
                f"Marker={MARKER}; nonce={NONCE}; objective unit={OBJECTIVE_UNIT}."
            ),
            "backend": self.config.backend,
            "random_seed": self.config.random_seed,
            "batch_size": self.config.default_batch_size,
            "initial_design_size": self.config.initial_design_size,
            "acquisition_method": self.config.acquisition_method,
            "parameters": [
                {
                    "name": name,
                    "type": "continuous",
                    "bounds": {"lower": 0.0, "upper": 1.0},
                    "description": "Normalized Ackley coordinate.",
                }
                for name in PARAMETER_NAMES
            ],
            "objectives": [
                {
                    "name": OBJECTIVE_NAME,
                    "direction": OBJECTIVE_DIRECTION,
                    "unit": OBJECTIVE_UNIT,
                }
            ],
        }

    def validate_local_evaluator(self) -> None:
        center = {name: 0.5 for name in PARAMETER_NAMES}
        corner = {name: 0.0 for name in PARAMETER_NAMES}
        center_eval = evaluate_ackley_6d(center)
        corner_eval = evaluate_ackley_6d(corner)
        if abs(center_eval["surface_response"] - 1.0) > 1e-12:
            raise RuntimeError(f"Ackley center check failed: {center_eval}")
        if not (0.0 <= corner_eval["surface_response"] < 0.2):
            raise RuntimeError(f"Ackley corner sanity check failed: {corner_eval}")

    def ensure_campaign(self, campaign_id: str | None) -> str:
        if campaign_id:
            return campaign_id
        intake = self.build_intake()
        validation = self.client.validate_intake(intake)
        if not validation.get("valid"):
            raise RuntimeError(f"Campaign intake validation failed: {validation}")
        create = self.client.create_campaign(
            intake,
            idempotency_key=BoMcpClient.make_idempotency_key(
                "ackley-create", MARKER, NONCE, self.config.invocation_label, str(self.config.random_seed)
            ),
        )
        if not create.get("success"):
            raise RuntimeError(f"Campaign creation failed: {create}")
        campaign_id = create.get("campaign_id")
        if not campaign_id:
            raise RuntimeError(f"Missing campaign_id in create response: {create}")
        return campaign_id

    def resume_if_needed(self, campaign_id: str) -> dict[str, Any]:
        status = self.client.next_action(campaign_id)
        status_name = str(status.get("status") or "").upper()
        if status_name == "PAUSED":
            self.client.lifecycle(campaign_id, action="resume")
            status = self.client.next_action(campaign_id)
        elif status_name == "COMPLETED":
            self.client.lifecycle(campaign_id, action="reopen")
            status = self.client.next_action(campaign_id)
        return status

    def artifact_dir(self, campaign_id: str) -> Path:
        path = self.workspace / "artifacts" / self.campaign_slug / campaign_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_manifest(self, latest_artifact_dir: Path) -> None:
        manifest = {
            "campaign_slug": self.campaign_slug,
            "package_modules": [
                "ackley_synth_6d.__init__",
                "ackley_synth_6d.ackley",
                "ackley_synth_6d.campaign",
            ],
            "run_entrypoint": "run_ackley_synth_6d.py",
            "latest_artifact_dir": str(latest_artifact_dir.relative_to(self.workspace)),
        }
        (self.workspace / "campaign_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def fetch_server_results(self, campaign_id: str) -> list[dict[str, Any]]:
        rows = self.client.get_results(campaign_id)
        enriched: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            params = {name: float(row["parameter_values"][name]) for name in PARAMETER_NAMES}
            evaluated = evaluate_ackley_6d(params)
            enriched.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": params,
                    "objective_values": {OBJECTIVE_NAME: float(row["objective_values"][OBJECTIVE_NAME])},
                    "status": "success",
                    "failure_reason": "",
                    "raw_response": float(evaluated["raw_response"]),
                    "surface_response": float(evaluated["surface_response"]),
                    "suggestion_id": row.get("suggestion_id", ""),
                    "result_id": row.get("result_id", ""),
                    "created_at": row.get("created_at", ""),
                }
            )
        return enriched

    def write_snapshot_artifacts(self, artifact_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
        csv_path = artifact_dir / "evaluations_latest.csv"
        with csv_path.open("w", newline="") as handle:
            fieldnames = [
                "evaluation_index",
                *PARAMETER_NAMES,
                OBJECTIVE_NAME,
                "status",
                "failure_reason",
                "raw_response",
                "surface_response",
                "suggestion_id",
                "result_id",
                "created_at",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                out = {
                    "evaluation_index": row["evaluation_index"],
                    OBJECTIVE_NAME: row["objective_values"][OBJECTIVE_NAME],
                    "status": row["status"],
                    "failure_reason": row["failure_reason"],
                    "raw_response": row["raw_response"],
                    "surface_response": row["surface_response"],
                    "suggestion_id": row.get("suggestion_id", ""),
                    "result_id": row.get("result_id", ""),
                    "created_at": row.get("created_at", ""),
                }
                out.update(row["parameter_values"])
                writer.writerow(out)
        (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def append_attempt_artifact(self, artifact_dir: Path, row: dict[str, Any]) -> None:
        path = artifact_dir / "evaluation_attempts.jsonl"
        with path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")

    def summarize(self, rows: list[dict[str, Any]], campaign_id: str, config_dict: dict[str, Any]) -> dict[str, Any]:
        successes = [row for row in rows if row["status"] == "success"]
        best = max(successes, key=lambda row: row["surface_response"]) if successes else None
        return {
            "campaign_id": campaign_id,
            "marker": MARKER,
            "nonce": NONCE,
            "objective_name": OBJECTIVE_NAME,
            "objective_direction": OBJECTIVE_DIRECTION,
            "objective_unit": OBJECTIVE_UNIT,
            "attempted_evaluations": len(rows),
            "successful_evaluations": len(successes),
            "config": config_dict,
            "best": {
                "evaluation_index": best["evaluation_index"] if best else None,
                "parameter_values": best["parameter_values"] if best else None,
                "raw_response": best["raw_response"] if best else None,
                "surface_response": best["surface_response"] if best else None,
            },
        }

    def point_seen_set(self, rows: list[dict[str, Any]]) -> set[tuple[float, ...]]:
        return {point_key(row["parameter_values"]) for row in rows if row["status"] == "success"}

    def _collect_unique_pending(
        self,
        campaign_id: str,
        remaining: int,
        seen_points: set[tuple[float, ...]],
    ) -> list[dict[str, Any]]:
        pending = self.client.query_suggestions(campaign_id, status_filter="pending", limit=500)
        unique: list[dict[str, Any]] = []
        batch_seen: set[tuple[float, ...]] = set()
        for suggestion in pending:
            key = point_key(suggestion["parameter_values"])
            if key in seen_points or key in batch_seen:
                self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                continue
            if len(unique) < remaining:
                unique.append(suggestion)
                batch_seen.add(key)
            else:
                self.client.update_suggestion_status(suggestion["suggestion_id"], "expired")
        return unique

    def get_unique_suggestions(
        self,
        campaign_id: str,
        remaining: int,
        seen_points: set[tuple[float, ...]],
    ) -> list[dict[str, Any]]:
        unique = self._collect_unique_pending(campaign_id, remaining, seen_points)
        while len(unique) < remaining:
            needed = remaining - len(unique)
            response = self.client.generate_suggestions(campaign_id, batch_size=needed, timeout_s=900.0)
            if not response.get("success"):
                raise RuntimeError(f"Suggestion generation failed: {response}")
            any_new = False
            batch_seen = {point_key(s["parameter_values"]) for s in unique}
            for suggestion in response.get("suggestions") or []:
                key = point_key(suggestion["parameter_values"])
                if key in seen_points or key in batch_seen:
                    self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                    continue
                unique.append(suggestion)
                batch_seen.add(key)
                any_new = True
            if not any_new:
                raise RuntimeError("BO-MCP returned only duplicate suggestions; aborting to avoid re-evaluation.")
        return unique[:remaining]

    def evaluate_and_submit(
        self,
        campaign_id: str,
        artifact_dir: Path,
        existing_rows: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        starting_index = len(existing_rows)
        rows = list(existing_rows)
        payload: list[dict[str, Any]] = []
        for offset, suggestion in enumerate(suggestions, start=1):
            params = {name: float(suggestion["parameter_values"][name]) for name in PARAMETER_NAMES}
            evaluated = evaluate_ackley_6d(params)
            row = {
                "evaluation_index": starting_index + offset,
                "parameter_values": params,
                "objective_values": {OBJECTIVE_NAME: float(evaluated["surface_response"])},
                "status": "success",
                "failure_reason": "",
                "raw_response": float(evaluated["raw_response"]),
                "surface_response": float(evaluated["surface_response"]),
                "suggestion_id": suggestion["suggestion_id"],
                "created_at": suggestion.get("created_at", ""),
            }
            self.append_attempt_artifact(artifact_dir, row)
            payload.append(
                {
                    "suggestion_id": suggestion["suggestion_id"],
                    "parameter_values": params,
                    "objective_values": {OBJECTIVE_NAME: float(evaluated["surface_response"])},
                    "metadata": {
                        "notes": f"Synthetic Ackley 6D evaluation. marker={MARKER}; nonce={NONCE}",
                        "experiment_id": f"ackley-eval-{starting_index + offset}",
                    },
                }
            )
            rows.append(row)
        submit = self.client.submit_results(
            campaign_id,
            results=payload,
            idempotency_key=BoMcpClient.make_idempotency_key(
                "ackley-submit", campaign_id, str(starting_index + 1), str(starting_index + len(payload))
            ),
        )
        if not submit.get("success"):
            raise RuntimeError(f"Result submission failed: {submit}")
        return rows

    def cleanup_pending(self, campaign_id: str) -> None:
        for suggestion in self.client.query_suggestions(campaign_id, status_filter="pending", limit=500):
            self.client.update_suggestion_status(suggestion["suggestion_id"], "expired")

    def pause_campaign(self, campaign_id: str) -> None:
        try:
            status = self.client.next_action(campaign_id)
            status_name = str(status.get("status") or "").upper()
            if status_name == "RUNNING":
                self.client.lifecycle(campaign_id, action="pause")
        except Exception:
            pass

    def run(self, campaign_id: str | None = None) -> dict[str, Any]:
        self.validate_local_evaluator()
        campaign_id = self.ensure_campaign(campaign_id)
        artifact_dir = self.artifact_dir(campaign_id)
        self.write_manifest(artifact_dir)
        config_dict = asdict(self.config)
        (artifact_dir / "run_config.json").write_text(json.dumps(config_dict, indent=2) + "\n")

        status = self.resume_if_needed(campaign_id)
        rows = self.fetch_server_results(campaign_id)
        attempted = len(rows)
        batches_run = 0

        while attempted < self.config.total_budget:
            if self.config.max_batches is not None and batches_run >= self.config.max_batches:
                break
            remaining = min(self.config.default_batch_size, self.config.total_budget - attempted)
            if status.get("action") not in (None, "bo_generate_suggestions") and attempted < self.config.total_budget:
                raise RuntimeError(f"Server declined further suggestions before budget completion: {status}")
            seen = self.point_seen_set(rows)
            suggestions = self.get_unique_suggestions(campaign_id, remaining, seen)
            rows = self.evaluate_and_submit(campaign_id, artifact_dir, rows, suggestions)
            attempted = len(rows)
            batches_run += 1
            status = self.client.next_action(campaign_id)
            summary = self.summarize(rows, campaign_id, config_dict)
            self.write_snapshot_artifacts(artifact_dir, rows, summary)

        self.cleanup_pending(campaign_id)
        diagnostics = self.client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=300.0)
        final_rows = self.fetch_server_results(campaign_id)
        final_summary = self.summarize(final_rows, campaign_id, config_dict)
        final_summary["diagnostics"] = diagnostics
        self.write_snapshot_artifacts(artifact_dir, final_rows, final_summary)
        self.pause_campaign(campaign_id)
        return final_summary
