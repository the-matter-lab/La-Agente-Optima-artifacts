"""Campaign orchestration — BO-MCP loop for the 6D Ackley benchmark.

Owns: intake construction, the BO loop, result recording, and reporting.
Does NOT own: CLI wiring, env setup, or Logfire configuration.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate
from .search_space import PARAM_NAMES, build_parameters

# ── constants ──────────────────────────────────────────────────────────
NONCE = "5e2a0e00-c88b-4a12-bc78-62161e987709"
MARKER = "akg-eval-884f9c5c3b2746eb87ab80c667e74db7"
CAMPAIGN_NAME = f"ackley6d-{MARKER}"
OBJECTIVE_NAME = "surface_response"
TOTAL_BUDGET = 60


# ── intake ─────────────────────────────────────────────────────────────
def build_intake() -> dict[str, Any]:
    """Return the BO-MCP campaign intake payload."""
    return {
        "name": CAMPAIGN_NAME,
        "description": (
            f"6D Ackley synthetic benchmark — maximize surface_response. "
            f"nonce={NONCE}"
        ),
        "parameters": build_parameters(),
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "backend": "botorch",
        "acquisition_method": "expected_improvement",
        "batch_size": 1,
        "initial_design_size": 12,
        "random_seed": 42,
    }


# ── result artifact writer ─────────────────────────────────────────────
class ArtifactWriter:
    """Append-only JSONL artifact with one row per evaluated candidate."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write_row(
        self,
        evaluation_index: int,
        parameter_values: dict[str, float],
        surface_response: float,
        raw_response: float,
        status: str,
        failure_reason: str | None = None,
        suggestion_id: str | None = None,
    ) -> None:
        row = {
            "evaluation_index": evaluation_index,
            "parameter_values": parameter_values,
            "objective_values": {OBJECTIVE_NAME: surface_response},
            "raw_response": raw_response,
            "status": status,
            "failure_reason": failure_reason,
            "suggestion_id": suggestion_id,
            "nonce": NONCE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(row) + "\n")


# ── main loop ──────────────────────────────────────────────────────────
def run_campaign(
    *,
    campaign_id: str | None = None,
    artifact_dir: Path,
    stop_file: Path | None = None,
    poll_s: float = 180,
    heartbeat_s: float = 1800,
) -> str:
    """Execute the full BO-MCP campaign loop.

    Returns the campaign_id.
    """
    client = BoMcpClient.from_env()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "ackley6d_results.jsonl"
    writer = ArtifactWriter(artifact_path)

    # ── create or resume ───────────────────────────────────────────────
    if campaign_id is None:
        intake = build_intake()
        # Validate first
        validation = client.validate_intake(intake)
        if not validation.get("success", True):
            print(
                f"[ALERT] Intake validation failed: {validation.get('errors', [])}",
                flush=True,
            )
            sys.exit(1)

        idem_key = BoMcpClient.make_idempotency_key("create", CAMPAIGN_NAME)
        resp = client.create_campaign(intake, idempotency_key=idem_key)
        if not resp.get("success", False):
            print(
                f"[ALERT] Campaign creation failed: {resp.get('errors', [])}",
                flush=True,
            )
            sys.exit(1)
        campaign_id = resp["campaign_id"]
        print(f"[EVENT] Campaign created: {campaign_id}", flush=True)
    else:
        # Resume: ensure campaign is running
        camp = client.get_campaign(campaign_id)
        status = camp.get("status", "")
        print(f"[EVENT] Resuming campaign {campaign_id} (status={status})", flush=True)
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            print("[EVENT] Campaign resumed", flush=True)
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            print("[EVENT] Campaign reopened", flush=True)

    # ── loop ───────────────────────────────────────────────────────────
    eval_count = 0
    last_heartbeat = time.monotonic()

    while eval_count < TOTAL_BUDGET:
        # Stop-file check
        if stop_file and stop_file.exists():
            print("[EVENT] Stop file detected — pausing campaign", flush=True)
            stop_file.unlink(missing_ok=True)
            # Submit any pending results first, then pause
            try:
                client.lifecycle(campaign_id, action="pause")
            except Exception:
                pass
            print("[EVENT] Campaign paused. Resume with same --campaign-id.", flush=True)
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            print(f"[HEARTBEAT] campaign={campaign_id} evaluated={eval_count}/{TOTAL_BUDGET}", flush=True)
            last_heartbeat = now

        # Ask server what to do next
        decision = client.next_action(campaign_id)
        action = decision.get("action", "")
        if action != "bo_generate_suggestions":
            reason = decision.get("reason", action)
            print(f"[EVENT] Server recommends stop: {reason}", flush=True)
            break

        # Generate suggestion
        remaining = TOTAL_BUDGET - eval_count
        batch = min(1, remaining)
        idem_key = BoMcpClient.make_idempotency_key(
            "suggest", campaign_id, str(eval_count)
        )
        try:
            sug_resp = client.generate_suggestions(
                campaign_id, batch_size=batch, timeout_s=poll_s
            )
        except Exception as exc:
            print(f"[ALERT] Suggestion generation error: {exc}", flush=True)
            # Re-query pending suggestions before retrying
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            if pending:
                sug_resp = {"success": True, "suggestions": pending}
            else:
                time.sleep(5)
                continue

        if not sug_resp.get("success", False):
            errors = sug_resp.get("errors", [])
            print(f"[ALERT] Suggestion generation failed: {errors}", flush=True)
            break

        suggestions = sug_resp.get("suggestions", [])
        if not suggestions:
            # No suggestions produced — check if budget exceeded
            print("[EVENT] No suggestions returned, checking next_action", flush=True)
            continue

        for suggestion in suggestions:
            if eval_count >= TOTAL_BUDGET:
                break

            eval_count += 1
            sid = suggestion.get("suggestion_id", "")
            params = suggestion.get("parameter_values", {})

            # Evaluate
            try:
                result = evaluate(params)
                raw_response = result["raw_response"]
                surface_response = result["surface_response"]
                status = "success"
                failure_reason = None
            except Exception as exc:
                raw_response = float("nan")
                surface_response = float("nan")
                status = "failed"
                failure_reason = str(exc)

            # Write artifact row
            writer.write_row(
                evaluation_index=eval_count,
                parameter_values={k: float(v) for k, v in params.items()},
                surface_response=surface_response if status == "success" else float("nan"),
                raw_response=raw_response if status == "success" else float("nan"),
                status=status,
                failure_reason=failure_reason,
                suggestion_id=sid,
            )

            # Submit result to BO-MCP
            if status == "success":
                result_payload = {
                    "parameter_values": {k: float(v) for k, v in params.items()},
                    "objective_values": {OBJECTIVE_NAME: surface_response},
                    "suggestion_id": sid,
                }
                idem_key = BoMcpClient.make_idempotency_key(
                    "result", campaign_id, str(eval_count)
                )
                try:
                    sub_resp = client.submit_results(
                        campaign_id,
                        results=[result_payload],
                        idempotency_key=idem_key,
                    )
                    if not sub_resp.get("success", False):
                        # Duplicate? Try with force
                        if "duplicate" in str(sub_resp.get("errors", [])).lower():
                            idem_key2 = BoMcpClient.make_idempotency_key(
                                "result-force", campaign_id, str(eval_count)
                            )
                            client.submit_results(
                                campaign_id,
                                results=[result_payload],
                                idempotency_key=idem_key2,
                                force=True,
                            )
                        else:
                            print(
                                f"[ALERT] Result submission failed: {sub_resp.get('errors', [])}",
                                flush=True,
                            )
                except Exception as exc:
                    print(f"[ALERT] Result submission exception: {exc}", flush=True)
            else:
                # Mark suggestion as rejected
                try:
                    client.update_suggestion_status(sid, status="rejected")
                except Exception:
                    pass

            print(
                f"[RESULT] eval={eval_count}/{TOTAL_BUDGET} "
                f"surface_response={surface_response:.6f} "
                f"raw_response={raw_response:.6f} "
                f"status={status} "
                f"params=[{', '.join(f'{k}={float(v):.4f}' for k, v in params.items())}]",
                flush=True,
            )

    # ── final report ───────────────────────────────────────────────────
    _print_final_report(campaign_id, artifact_path, client)

    # Pause campaign (not terminate — allows reopen/continue)
    try:
        client.lifecycle(campaign_id, action="pause")
        print(f"[EVENT] Campaign {campaign_id} paused.", flush=True)
    except Exception:
        pass

    return campaign_id


def _print_final_report(
    campaign_id: str, artifact_path: Path, client: BoMcpClient
) -> None:
    """Read the artifact and print a summary."""
    rows: list[dict] = []
    if artifact_path.exists():
        with open(artifact_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    successful = [r for r in rows if r["status"] == "success"]
    attempted = len(rows)

    if successful:
        best = max(successful, key=lambda r: r["objective_values"][OBJECTIVE_NAME])
        best_params = best["parameter_values"]
        best_sr = best["objective_values"][OBJECTIVE_NAME]
        best_raw = best["raw_response"]
        print(
            f"[RESULT] BEST surface_response={best_sr:.6f}  "
            f"raw_response={best_raw:.6f}  "
            f"params=[{', '.join(f'{k}={v:.6f}' for k, v in best_params.items())}]",
            flush=True,
        )
    print(
        f"[RESULT] SUMMARY campaign_id={campaign_id} "
        f"successful={len(successful)} attempted={attempted} budget={TOTAL_BUDGET}",
        flush=True,
    )
