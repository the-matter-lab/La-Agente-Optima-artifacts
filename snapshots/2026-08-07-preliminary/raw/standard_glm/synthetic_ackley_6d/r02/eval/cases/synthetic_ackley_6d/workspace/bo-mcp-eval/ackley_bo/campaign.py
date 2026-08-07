"""Campaign intake construction and BO-MCP orchestration."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .evaluator import evaluate
from .reporting import build_artifact_row, write_artifact, write_summary

# ── constants ──────────────────────────────────────────────────────────
CAMPAIGN_MARKER = "akg-eval-1115ffcb87fa4a6dbb0454263fb25553"
CACHE_BUSTER = "221d8dd7-74d6-4aa1-91de-bc9e69d726c3"
BUDGET = 60  # max attempted evaluations


def build_intake() -> dict[str, Any]:
    """Return the campaign intake payload for the 6-D Ackley benchmark."""
    parameters = [
        {
            "name": f"x_{i}",
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
        }
        for i in range(1, 7)
    ]

    return {
        "name": f"ackley-6d-{CAMPAIGN_MARKER}",
        "description": (
            f"Ackley 6-D synthetic benchmark (maximize surface_response). "
            f"cache-buster={CACHE_BUSTER}"
        ),
        "parameters": parameters,
        "objectives": [
            {
                "name": "surface_response",
                "direction": "maximize",
                "unit": "normalized_unitless",
            }
        ],
        "backend": "botorch",
        "random_seed": 2024,
        "initial_design_size": 10,
        "batch_size": 1,
        "acquisition_method": "expected_improvement",
    }


def _find_or_create_campaign(
    client: BoMcpClient, intake: dict[str, Any], campaign_id: str | None
) -> str:
    """Return a campaign_id, creating the campaign if needed."""
    if campaign_id:
        # Verify it exists and belongs to this invocation.
        try:
            info = client.get_campaign(campaign_id)
            name = info.get("name", "")
            if CAMPAIGN_MARKER not in name:
                print(
                    f"[ALERT] Campaign {campaign_id} lacks marker {CAMPAIGN_MARKER}; "
                    f"refusing to adopt it.",
                    flush=True,
                )
                sys.exit(1)
            print(f"[EVENT] Resuming existing campaign {campaign_id}", flush=True)
            return campaign_id
        except BoMcpClientError:
            print(
                f"[ALERT] Campaign {campaign_id} not found; creating a new one.",
                flush=True,
            )

    idem_key = f"ackley-create-{uuid.uuid4().hex[:12]}"
    resp = client.create_campaign(intake, idempotency_key=idem_key)
    cid = resp.get("campaign_id")
    if not cid:
        print(f"[ALERT] Campaign creation failed: {resp}", flush=True)
        sys.exit(1)
    print(f"[EVENT] Created campaign {cid}", flush=True)
    return cid


def run_campaign(
    *,
    campaign_id: str | None = None,
    artifact_dir: str = ".",
    stop_file: str = "STOP",
    poll_s: float = 180.0,
    heartbeat_s: float = 1800.0,
) -> str:
    """Execute the BO loop and return the campaign_id."""
    client = BoMcpClient.from_env(timeout_s=120.0)
    intake = build_intake()
    cid = _find_or_create_campaign(client, intake, campaign_id)

    # Ensure campaign is running (resume if paused, reopen if completed).
    status_info = client.next_action(cid)
    status = status_info.get("status", "")
    if status == "paused":
        client.lifecycle(cid, action="resume")
        print(f"[EVENT] Resumed paused campaign {cid}", flush=True)
    elif status in ("completed", "terminated"):
        client.lifecycle(cid, action="reopen")
        print(f"[EVENT] Reopened completed campaign {cid}", flush=True)

    attempted = 0
    successful = 0
    best_surface = -float("inf")
    best_raw = None
    best_params = None
    last_heartbeat = time.time()
    artifact_rows: list[dict[str, Any]] = []

    # Load any previously persisted rows (for resume scenarios).
    artifact_path = os.path.join(artifact_dir, "ackley_results.jsonl")
    if os.path.exists(artifact_path):
        with open(artifact_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    artifact_rows.append(row)
                    if row.get("status") == "success":
                        successful += 1
                        sr = row["objective_values"]["surface_response"]
                        if sr > best_surface:
                            best_surface = sr
                            best_raw = row.get("raw_response")
                            best_params = row["parameter_values"]
                    attempted += 1
        print(
            f"[EVENT] Loaded {attempted} prior evaluations "
            f"({successful} successful) from artifact",
            flush=True,
        )

    print(
        f"[EVENT] Starting BO loop  budget={BUDGET}  "
        f"attempted={attempted}  successful={successful}",
        flush=True,
    )

    while attempted < BUDGET:
        # ── stop-file check ────────────────────────────────────────
        if os.path.exists(stop_file):
            print(
                f"[EVENT] Stop file '{stop_file}' detected — pausing campaign",
                flush=True,
            )
            try:
                os.remove(stop_file)
            except OSError:
                pass
            # Pause only if still running.
            cur = client.next_action(cid)
            if cur.get("status") == "running":
                client.lifecycle(cid, action="pause")
            break

        # ── heartbeat ──────────────────────────────────────────────
        now = time.time()
        if now - last_heartbeat >= heartbeat_s:
            print(
                f"[HEARTBEAT] campaign={cid} attempted={attempted} "
                f"successful={successful} best_surface={best_surface:.6f}",
                flush=True,
            )
            last_heartbeat = now

        # ── ask server what to do ──────────────────────────────────
        decision = client.next_action(cid)
        action = decision.get("action", "")

        # Collect suggestions to evaluate this iteration.
        suggestions: list[dict[str, Any]] = []

        if action == "bo_submit_results":
            # Pending suggestions exist — fetch and evaluate them.
            try:
                suggestions = client.query_suggestions(
                    cid, status_filter="pending"
                )
            except (BoMcpClientError, BoMcpOperationError) as exc:
                print(f"[ALERT] Query pending suggestions failed: {exc}", flush=True)
                time.sleep(min(poll_s, 30))
                continue
            if not suggestions:
                # No pending suggestions despite the recommendation — generate.
                action = "bo_generate_suggestions"

        if action == "bo_generate_suggestions":
            remaining = BUDGET - attempted
            batch = min(1, remaining)
            if batch < 1:
                break
            try:
                gen_resp = client.generate_suggestions(cid, batch_size=batch)
            except (BoMcpClientError, BoMcpOperationError) as exc:
                print(f"[ALERT] Suggestion generation failed: {exc}", flush=True)
                time.sleep(min(poll_s, 30))
                continue
            suggestions = gen_resp.get("suggestions", [])
            if not suggestions:
                errors = gen_resp.get("errors", [])
                print(f"[ALERT] No suggestions returned: {errors}", flush=True)
                time.sleep(min(poll_s, 30))
                continue

        elif action not in ("bo_submit_results",):
            reason = decision.get("reason", "unknown")
            print(
                f"[EVENT] Server recommends '{action}' (reason: {reason}) — "
                f"stopping loop",
                flush=True,
            )
            break


        # ── evaluate each suggestion ───────────────────────────────
        # ── evaluate each suggestion ───────────────────────────────
        for sug in suggestions:
            if attempted >= BUDGET:
                break

            sid = sug["suggestion_id"]
            params = sug["parameter_values"]
            attempted += 1
            eval_idx = attempted

            try:
                result = evaluate(params)
                raw_resp = result["raw_response"]
                surf_resp = result["surface_response"]

                # Submit result to BO-MCP.
                idem_key = BoMcpClient.make_idempotency_key(
                    "ackley-res", cid, str(eval_idx)
                )
                client.submit_results(
                    cid,
                    results=[
                        {
                            "suggestion_id": sid,
                            "parameter_values": params,
                            "objective_values": {"surface_response": surf_resp},
                        }
                    ],
                    idempotency_key=idem_key,
                )

                successful += 1
                if surf_resp > best_surface:
                    best_surface = surf_resp
                    best_raw = raw_resp
                    best_params = params

                row = build_artifact_row(
                    eval_index=eval_idx,
                    parameter_values=params,
                    surface_response=surf_resp,
                    raw_response=raw_resp,
                    status="success",
                    failure_reason=None,
                )
                artifact_rows.append(row)
                write_artifact(artifact_dir, row)

                print(
                    f"[RESULT] eval={eval_idx} surface_response={surf_resp:.6f} "
                    f"raw_response={raw_resp:.6f} "
                    f"best_surface={best_surface:.6f}",
                    flush=True,
                )

            except Exception as exc:
                # Record failure but continue within budget.
                row = build_artifact_row(
                    eval_index=eval_idx,
                    parameter_values=params,
                    surface_response=None,
                    raw_response=None,
                    status="failed",
                    failure_reason=str(exc),
                )
                artifact_rows.append(row)
                write_artifact(artifact_dir, row)

                # Mark suggestion as rejected so BO can move on.
                try:
                    client.update_suggestion_status(sid, "rejected")
                except Exception:
                    pass

                print(
                    f"[ALERT] eval={eval_idx} FAILED: {exc}",
                    flush=True,
                )

    # ── end-of-run ─────────────────────────────────────────────────
    print(
        f"\n[EVENT] Campaign loop finished  "
        f"attempted={attempted}  successful={successful}",
        flush=True,
    )

    if best_params is not None:
        write_summary(
            artifact_dir,
            best_params=best_params,
            best_raw_response=best_raw,
            best_surface_response=best_surface,
            attempted=attempted,
            successful=successful,
            rows=artifact_rows,
        )
        print(
            f"[RESULT] best_surface_response={best_surface:.6f}  "
            f"best_raw_response={best_raw:.6f}  "
            f"best_params={best_params}",
            flush=True,
        )

    # Pause the campaign at end of invocation.
    cur = client.next_action(cid)
    if cur.get("status") == "running":
        client.lifecycle(cid, action="pause")
        print(f"[EVENT] Paused campaign {cid}", flush=True)

    return cid
