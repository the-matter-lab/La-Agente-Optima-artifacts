from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from . import CACHE_BUSTER_NONCE, OBJECTIVE_NAME, OWNERSHIP_MARKER
from .evaluator import OracleEvaluationError, evaluate_candidate
from .intake import build_campaign_name, build_intake
from .reporting import (
    append_attempt_record,
    attempted_count_from_suggestions,
    build_summary,
    ensure_artifact_dir,
    write_summary,
)
from .search_space import normalize_parameter_values


@dataclass(frozen=True)
class RunConfig:
    campaign_id: str | None
    campaign_label: str | None
    artifact_root: Path
    stop_file: Path
    poll_s: int
    heartbeat_s: int
    max_attempts: int
    oracle_timeout_s: float
    suggestion_timeout_s: float


class CampaignRunner:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.client = BoMcpClient.from_env(timeout_s=120.0)
        self.artifact_root = config.artifact_root
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("direct_arylation_campaign")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self._last_heartbeat = time.monotonic()

    def run(self) -> int:
        campaign = self._resolve_campaign()
        artifact_dir = ensure_artifact_dir(self.artifact_root, campaign["id"])
        self._attach_file_logger(artifact_dir / "run.log")
        attempts_path = artifact_dir / "attempts.jsonl"
        summary_path = artifact_dir / "summary.json"
        self._event(f"campaign_ready id={campaign['id']} name={campaign['name']}")
        logfire.info("campaign ready", campaign_id=campaign["id"], campaign_name=campaign["name"])

        while True:
            self._maybe_heartbeat(campaign["id"])
            if self.config.stop_file.exists():
                self._event(f"stop_file_detected path={self.config.stop_file}")
                self.config.stop_file.unlink(missing_ok=True)
                break

            suggestions = self.client.query_suggestions(campaign["id"], status_filter=None, limit=500)
            attempted_count = attempted_count_from_suggestions(suggestions)
            if attempted_count >= self.config.max_attempts:
                self._event(f"attempt_budget_exhausted attempted={attempted_count} limit={self.config.max_attempts}")
                break

            pending = [item for item in suggestions if item.get("status") == "pending"]
            suggestion = pending[0] if pending else None
            if suggestion is None:
                decision = self.client.next_action(campaign["id"])
                if decision.get("action") != "bo_generate_suggestions":
                    self._event(
                        "server_stopped_generating "
                        f"status={decision.get('status')} action={decision.get('action')} reason={decision.get('reason')}"
                    )
                    break
                suggestion = self._generate_one(campaign["id"])
            else:
                self._event(f"reusing_pending_suggestion suggestion_id={suggestion['suggestion_id']}")

            normalized = normalize_parameter_values(dict(suggestion.get("parameter_values") or {}))
            next_attempt_number = attempted_count + 1
            try:
                oracle_result = evaluate_candidate(normalized, timeout_s=self.config.oracle_timeout_s)
                result_payload = {
                    "parameter_values": normalized,
                    "objective_values": {OBJECTIVE_NAME: oracle_result.measured_yield},
                    "suggestion_id": suggestion["suggestion_id"],
                }
                self._submit_result(campaign["id"], result_payload)
                attempt_record = {
                    "attempt_index": next_attempt_number,
                    "campaign_id": campaign["id"],
                    "suggestion_id": suggestion["suggestion_id"],
                    "status": "succeeded",
                    "parameter_values": normalized,
                    "objective_values": {OBJECTIVE_NAME: oracle_result.measured_yield},
                    "oracle_status_code": oracle_result.status_code,
                }
                append_attempt_record(attempts_path, attempt_record)
                self._result(
                    f"attempt={next_attempt_number} status=succeeded yield={oracle_result.measured_yield:.4f} "
                    f"params={json.dumps(normalized, sort_keys=True)}"
                )
                logfire.info(
                    "oracle success",
                    campaign_id=campaign["id"],
                    suggestion_id=suggestion["suggestion_id"],
                    measured_yield=oracle_result.measured_yield,
                )
            except OracleEvaluationError as exc:
                self.client.update_suggestion_status(suggestion["suggestion_id"], "rejected")
                attempt_record = {
                    "attempt_index": next_attempt_number,
                    "campaign_id": campaign["id"],
                    "suggestion_id": suggestion["suggestion_id"],
                    "status": "failed",
                    "parameter_values": normalized,
                    "objective_values": None,
                    "error": str(exc),
                }
                append_attempt_record(attempts_path, attempt_record)
                self._alert(
                    f"attempt={next_attempt_number} status=failed suggestion_id={suggestion['suggestion_id']} error={exc}"
                )
                logfire.info(
                    "oracle failure",
                    campaign_id=campaign["id"],
                    suggestion_id=suggestion["suggestion_id"],
                    error=str(exc),
                )
            campaign = self.client.get_campaign(campaign["id"])
            self._refresh_summary(campaign, summary_path)

        campaign = self.client.get_campaign(campaign["id"])
        self._refresh_summary(campaign, summary_path)
        campaign = self._pause_if_needed(campaign)
        self._refresh_summary(campaign, summary_path)
        self._event(
            f"shutdown campaign_id={campaign['id']} status={campaign['status']} artifact_dir={artifact_dir} nonce={CACHE_BUSTER_NONCE}"
        )
        return 0

    def _resolve_campaign(self) -> dict[str, Any]:
        if self.config.campaign_id:
            campaign = self.client.get_campaign(self.config.campaign_id)
            self._ensure_marker(campaign["name"])
            status = campaign.get("status")
            if status == "paused":
                self.client.lifecycle(campaign["id"], action="resume")
                campaign = self.client.get_campaign(campaign["id"])
            elif status == "completed":
                self.client.lifecycle(campaign["id"], action="reopen")
                campaign = self.client.get_campaign(campaign["id"])
            return campaign

        campaign_name = build_campaign_name(self.config.campaign_label)
        self._ensure_marker(campaign_name)
        intake = build_intake(campaign_name)
        self.client.validate_intake(intake)
        created = self.client.create_campaign(
            intake,
            idempotency_key=BoMcpClient.make_idempotency_key("create", campaign_name, CACHE_BUSTER_NONCE),
        )
        campaign_id = created.get("campaign_id")
        if not campaign_id:
            raise RuntimeError(f"BO-MCP did not return campaign_id: {created}")
        return self.client.get_campaign(campaign_id)

    def _generate_one(self, campaign_id: str) -> dict[str, Any]:
        try:
            generated = self.client.generate_suggestions(
                campaign_id,
                batch_size=1,
                timeout_s=self.config.suggestion_timeout_s,
            )
            suggestions = list(generated.get("suggestions") or [])
            if not suggestions:
                raise RuntimeError(f"No suggestions returned: {generated}")
            suggestion = suggestions[0]
            self._event(f"generated_suggestion suggestion_id={suggestion['suggestion_id']}")
            return suggestion
        except BoMcpClientError:
            pending = self.client.query_suggestions(campaign_id, status_filter="pending", limit=500)
            if pending:
                suggestion = pending[0]
                self._event(f"recovered_pending_after_generation_error suggestion_id={suggestion['suggestion_id']}")
                return suggestion
            self._event(f"generation_retry_wait seconds={self.config.poll_s}")
            time.sleep(self.config.poll_s)
            pending = self.client.query_suggestions(campaign_id, status_filter="pending", limit=500)
            if pending:
                suggestion = pending[0]
                self._event(f"recovered_pending_after_wait suggestion_id={suggestion['suggestion_id']}")
                return suggestion
            raise

    def _submit_result(self, campaign_id: str, result_payload: dict[str, Any]) -> None:
        key = BoMcpClient.make_idempotency_key(
            "submit",
            campaign_id,
            result_payload["suggestion_id"],
            CACHE_BUSTER_NONCE,
        )
        try:
            self.client.submit_results(campaign_id, results=[result_payload], idempotency_key=key)
        except BoMcpOperationError as exc:
            if exc.payload.get("duplicates_detected"):
                force_key = BoMcpClient.make_idempotency_key(
                    "submit-force",
                    campaign_id,
                    result_payload["suggestion_id"],
                    CACHE_BUSTER_NONCE,
                )
                self.client.submit_results(
                    campaign_id,
                    results=[result_payload],
                    idempotency_key=force_key,
                    force=True,
                )
                self._event(f"forced_replicate_submission suggestion_id={result_payload['suggestion_id']}")
                return
            raise

    def _refresh_summary(self, campaign: dict[str, Any], summary_path: Path) -> None:
        suggestions = self.client.query_suggestions(campaign["id"], status_filter=None, limit=500)
        results = self.client.get_results(campaign["id"])
        summary = build_summary(campaign=campaign, suggestions=suggestions, results=results)
        write_summary(summary_path, summary)

    def _pause_if_needed(self, campaign: dict[str, Any]) -> dict[str, Any]:
        if campaign.get("status") in {"running", "idle"}:
            self.client.lifecycle(campaign["id"], action="pause")
            return self.client.get_campaign(campaign["id"])
        return campaign

    def _ensure_marker(self, campaign_name: str) -> None:
        if OWNERSHIP_MARKER not in campaign_name:
            raise RuntimeError(
                f"Campaign name must include ownership marker {OWNERSHIP_MARKER!r}: {campaign_name!r}"
            )

    def _attach_file_logger(self, log_path: Path) -> None:
        if any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path for handler in self.logger.handlers):
            return
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _event(self, message: str) -> None:
        print(f"[EVENT] {message}", flush=True)
        self.logger.info(message)
        logfire.info("event", message=message)

    def _alert(self, message: str) -> None:
        print(f"[ALERT] {message}", flush=True)
        self.logger.warning(message)
        logfire.info("alert", message=message)

    def _result(self, message: str) -> None:
        print(f"[RESULT] {message}", flush=True)
        self.logger.info(message)
        logfire.info("result", message=message)

    def _maybe_heartbeat(self, campaign_id: str) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < self.config.heartbeat_s:
            return
        summary = self.client.get_campaign(campaign_id)
        print(
            f"[HEARTBEAT] campaign_id={campaign_id} status={summary['status']} iteration={summary['iteration']}",
            flush=True,
        )
        self.logger.info("heartbeat campaign_id=%s status=%s iteration=%s", campaign_id, summary["status"], summary["iteration"])
        logfire.info(
            "heartbeat",
            campaign_id=campaign_id,
            status=summary["status"],
            iteration=summary["iteration"],
        )
        self._last_heartbeat = now


def run_campaign(config: RunConfig) -> int:
    if not os.getenv("BO_MCP_API_URL"):
        raise RuntimeError("BO_MCP_API_URL is required")
    if not os.getenv("BO_MCP_API_KEY"):
        raise RuntimeError("BO_MCP_API_KEY is required")
    runner = CampaignRunner(config)
    return runner.run()
