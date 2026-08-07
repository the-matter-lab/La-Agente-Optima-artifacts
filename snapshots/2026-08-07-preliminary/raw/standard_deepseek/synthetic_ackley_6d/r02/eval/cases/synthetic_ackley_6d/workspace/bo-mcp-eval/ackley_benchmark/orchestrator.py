"""Campaign orchestrator: the BO-MCP loop for the Ackley benchmark."""

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError

from .evaluator import evaluate
from .intake import build_intake, make_idempotency_key, OWNERSHIP_MARKER
from .reporting import (
    build_result_row,
    extract_objective,
    print_final_report,
    write_results_artifact,
)

logger = logging.getLogger(__name__)

# Timeout for a single generate_suggestions call.  The BayBE backend fits a GP
# whose cost grows with the result count; 5 minutes is generous for 6-D with
# ~60 points while still failing fast enough to retry.
_GENERATE_TIMEOUT_S = 300.0

# Maximum retries for a generate_suggestions call that times out or fails
# transiently.  Each retry first queries for pending suggestions (the server
# may have produced them despite the client-side timeout).
_MAX_GENERATE_RETRIES = 3


def _param_tuple(pv: dict[str, float]) -> tuple:
    """Hashable representation of parameter values for dedup."""
    return tuple(pv[f"x_{i}"] for i in range(1, 7))


def _generate_with_retry(
    client: BoMcpClient,
    campaign_id: str,
    batch_size: int,
    *,
    poll_s: int,
) -> dict[str, Any] | None:
    """Call generate_suggestions with timeout and retry logic.

    On timeout, queries pending suggestions before retrying — the server
    may have produced them despite the client-side timeout.
    Returns the generate response dict, or None after exhausting retries.
    """
    last_error = None
    for attempt in range(1, _MAX_GENERATE_RETRIES + 1):
        try:
            gen_resp = client.generate_suggestions(
                campaign_id,
                batch_size=batch_size,
                timeout_s=_GENERATE_TIMEOUT_S,
            )
            return gen_resp
        except requests.exceptions.Timeout:
            last_error = f"timeout after {_GENERATE_TIMEOUT_S}s"
            print(
                f"[ALERT] generate_suggestions timed out "
                f"(attempt {attempt}/{_MAX_GENERATE_RETRIES}) — "
                f"checking for pending suggestions"
            )
            logger.warning(
                "generate_suggestions timeout attempt=%d/%d", attempt, _MAX_GENERATE_RETRIES
            )
            # Query pending — server may have finished despite our timeout
            try:
                pending = client.query_suggestions(campaign_id, status_filter="pending")
                if pending:
                    print(f"[EVENT] Found {len(pending)} pending suggestion(s) after timeout")
                    return {"success": True, "suggestions": pending, "iteration": None}
            except Exception:
                pass
            if attempt < _MAX_GENERATE_RETRIES:
                backoff = min(30 * attempt, 120)
                print(f"[EVENT] Retrying generate_suggestions in {backoff}s")
                time.sleep(backoff)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(
                f"[ALERT] generate_suggestions request error "
                f"(attempt {attempt}/{_MAX_GENERATE_RETRIES}): {e}"
            )
            logger.error("generate_suggestions request error attempt=%d: %s", attempt, e)
            if attempt < _MAX_GENERATE_RETRIES:
                backoff = min(30 * attempt, 120)
                time.sleep(backoff)
        except BoMcpOperationError as e:
            # Operation-level rejection — not retryable
            print(f"[ALERT] Suggestion generation rejected: {e}")
            logger.error("generate_suggestions rejected: %s", e)
            return None

    print(f"[ALERT] generate_suggestions failed after {_MAX_GENERATE_RETRIES} attempts: {last_error}")
    return None


def _evaluate_and_submit(
    client: BoMcpClient,
    campaign_id: str,
    suggestions: list[dict],
    *,
    seen_params: set[tuple],
    results_rows: list[dict],
    attempted: int,
    max_attempted: int,
) -> tuple[int, list[dict]]:
    """Evaluate a list of suggestions and submit results.

    Returns (new_attempted, batch_results_for_submission).
    """
    batch_results: list[dict] = []
    for sug in suggestions:
        if attempted >= max_attempted:
            break

        sid = sug["suggestion_id"]
        pv = sug["parameter_values"]
        pt = _param_tuple(pv)

        if pt in seen_params:
            print(f"[EVENT] Duplicate suggestion {sid} — rejecting")
            try:
                client.update_suggestion_status(sid, status="rejected")
            except BoMcpOperationError:
                pass
            continue

        seen_params.add(pt)
        attempted += 1

        try:
            eval_result = evaluate(pv)
        except Exception as exc:
            eval_result = {
                "raw_response": None,
                "surface_response": None,
                "status": "failed",
                "failure_reason": str(exc),
            }
            print(f"[ALERT] Evaluation failed for suggestion {sid}: {exc}")
            logger.error("eval failed sid=%s: %s", sid, exc)

        row = build_result_row(attempted, pv, eval_result, suggestion_id=sid)
        results_rows.append(row)

        if eval_result["status"] == "completed":
            batch_results.append({
                "suggestion_id": sid,
                "parameter_values": pv,
                "objective_values": extract_objective(eval_result),
            })
            print(
                f"[RESULT] idx={attempted:3d}  "
                f"surface_response={eval_result['surface_response']:.6f}  "
                f"raw_response={eval_result['raw_response']:.6f}"
            )
        else:
            try:
                client.update_suggestion_status(sid, status="rejected")
            except BoMcpOperationError:
                pass
            print(f"[RESULT] idx={attempted:3d}  status=failed  reason={eval_result.get('failure_reason')}")

    # Submit if we have results
    if batch_results:
        try:
            sub_resp = client.submit_results(
                campaign_id,
                results=batch_results,
                idempotency_key=make_idempotency_key(f"sub-{campaign_id}"),
            )
            if sub_resp.get("success"):
                print(f"[EVENT] Submitted {len(batch_results)} result(s)")
            else:
                print(f"[ALERT] Submission rejected: {sub_resp.get('errors')}")
                logger.error("submit_results rejected: %s", sub_resp.get("errors"))
        except BoMcpOperationError as e:
            print(f"[ALERT] Submission failed: {e}")
            logger.error("submit_results failed: %s", e)

    return attempted, batch_results


def run_campaign(
    *,
    max_attempted: int = 60,
    poll_s: int = 180,
    heartbeat_s: int = 1800,
    stop_file: str | None = None,
    campaign_id: str | None = None,
    artifact_dir: str = "artifacts",
    log_path: str = "campaign.log",
) -> None:
    """Execute the BO-MCP campaign loop.

    Args:
        max_attempted: Maximum attempted evaluations (CLI budget, not intake cap).
        poll_s: Seconds between heartbeat lines.
        heartbeat_s: Seconds between heartbeat lines.
        stop_file: Path to a stop marker file; checked before each suggestion.
        campaign_id: Resume an existing campaign instead of creating one.
        artifact_dir: Directory for result artifacts.
        log_path: Path for the run log.
    """
    # --- setup ---
    os.makedirs(artifact_dir, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger.info("campaign start  max_attempted=%d  campaign_id=%s", max_attempted, campaign_id)

    # Use a generous client timeout so next_action / submit_results don't
    # trip over slow responses, but generate_suggestions gets its own
    # shorter timeout via _generate_with_retry.
    client = BoMcpClient.from_env(timeout_s=120.0)

    # --- create or resume ---
    if campaign_id:
        print(f"[EVENT] Resuming campaign {campaign_id}")
        logger.info("resuming campaign_id=%s", campaign_id)
        # Ensure it's running
        try:
            client.lifecycle(campaign_id, action="resume")
            print(f"[EVENT] Campaign {campaign_id} resumed")
        except BoMcpOperationError:
            # Might already be running; try reopen
            try:
                client.lifecycle(campaign_id, action="reopen")
                print(f"[EVENT] Campaign {campaign_id} reopened")
            except BoMcpOperationError as e:
                print(f"[EVENT] Could not resume/reopen: {e}")
    else:
        intake = build_intake()
        # Validate first
        client.validate_intake(intake)
        print("[EVENT] Intake validated")

        response = client.create_campaign(
            intake, idempotency_key=make_idempotency_key("create-ackley")
        )
        if not response.get("success"):
            raise RuntimeError(f"Campaign creation failed: {response.get('errors')}")
        campaign_id = response["campaign_id"]
        print(f"[EVENT] Campaign created: {campaign_id}")
        logger.info("created campaign_id=%s", campaign_id)

# --- loop state ---
    results_rows: list[dict] = []
    seen_params: set[tuple] = set()
    attempted = 0
    last_heartbeat = time.monotonic()

    # On resume, account for pre-existing results so the total budget is
    # honoured.  Also seed the dedup set from existing parameter values.
    if campaign_id:
        try:
            existing = client.get_results(campaign_id)
            pre_existing = len(existing)
            if pre_existing > 0:
                attempted = pre_existing
                for r in existing:
                    pv = r.get("parameter_values", {})
                    if pv:
                        seen_params.add(_param_tuple(pv))
                print(
                    f"[EVENT] Campaign has {pre_existing} pre-existing result(s); "
                    f"budget remaining: {max_attempted - attempted}"
                )
                logger.info(
                    "pre-existing results=%d  remaining budget=%d",
                    pre_existing, max_attempted - attempted,
                )
        except Exception as e:
            print(f"[EVENT] Could not read existing results: {e}")

    # --- main loop ---
    while attempted < max_attempted:
        # Stop-file check
        if stop_file and os.path.exists(stop_file):
            print(f"[EVENT] Stop file '{stop_file}' detected — shutting down")
            os.remove(stop_file)
            break

        # Heartbeat
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            print(f"[HEARTBEAT] attempted={attempted}/{max_attempted}  campaign={campaign_id}")
            last_heartbeat = now

        # Ask server what to do
        try:
            decision = client.next_action(campaign_id)
        except requests.exceptions.RequestException as e:
            print(f"[ALERT] next_action request failed: {e} — retrying in {poll_s}s")
            logger.error("next_action request failed: %s", e)
            time.sleep(poll_s)
            continue
        logger.debug("next_action: %s", decision)

        action = decision["action"]

        # --- bo_submit_results: pending suggestions exist, evaluate them ---
        if action == "bo_submit_results":
            print(f"[EVENT] Server: {decision.get('reason', 'pending suggestions awaiting results')}")
            pending = client.query_suggestions(campaign_id, status_filter="pending")
            if pending:
                print(f"[EVENT] Found {len(pending)} pending suggestion(s)")
                attempted, _ = _evaluate_and_submit(
                    client, campaign_id, pending,
                    seen_params=seen_params,
                    results_rows=results_rows,
                    attempted=attempted,
                    max_attempted=max_attempted,
                )
            else:
                print("[EVENT] No pending suggestions found — polling")
                time.sleep(poll_s)
            write_results_artifact(results_rows, artifact_dir)
            continue

        # --- bo_generate_suggestions: normal flow ---
        if action != "bo_generate_suggestions":
            print(f"[EVENT] Server says stop: action={action} reason={decision.get('reason')}")
            break

        # Generate suggestions (with timeout + retry)
        remaining = max_attempted - attempted
        batch_size = min(3, remaining)
        gen_resp = _generate_with_retry(
            client, campaign_id, batch_size, poll_s=poll_s
        )
        if gen_resp is None:
            print(f"[ALERT] Could not generate suggestions — polling in {poll_s}s")
            time.sleep(poll_s)
            continue

        if not gen_resp.get("success"):
            print(f"[ALERT] Suggestion generation rejected: {gen_resp.get('errors')}")
            logger.error("generate_suggestions rejected: %s", gen_resp.get("errors"))
            time.sleep(poll_s)
            continue

        suggestions = gen_resp.get("suggestions", [])
        if not suggestions:
            print("[EVENT] No suggestions returned — polling")
            time.sleep(poll_s)
            continue

        iteration_info = gen_resp.get("iteration")
        if iteration_info is not None:
            print(f"[EVENT] Got {len(suggestions)} suggestion(s)  iteration={iteration_info}")
        else:
            print(f"[EVENT] Got {len(suggestions)} suggestion(s) (from pending after timeout)")

        attempted, _ = _evaluate_and_submit(
            client, campaign_id, suggestions,
            seen_params=seen_params,
            results_rows=results_rows,
            attempted=attempted,
            max_attempted=max_attempted,
        )

        # Write incremental artifact
        write_results_artifact(results_rows, artifact_dir)

    # --- shutdown ---
    print(f"[EVENT] Loop finished  attempted={attempted}  campaign={campaign_id}")

    # Pause the campaign (don't terminate)
    try:
        campaign_status = client.next_action(campaign_id).get("status", "unknown")
        if campaign_status == "running":
            client.lifecycle(campaign_id, action="pause")
            print(f"[EVENT] Campaign {campaign_id} paused")
    except BoMcpOperationError as e:
        print(f"[EVENT] Could not pause campaign: {e}")

    # Final artifact
    artifact_path = write_results_artifact(results_rows, artifact_dir)
    print(f"[EVENT] Results artifact: {artifact_path}")

    # Final report
    print_final_report(results_rows)

    # Diagnostics (expensive — call once at end with long timeout)
    try:
        diag_client = BoMcpClient.from_env(timeout_s=300.0)
        diag = diag_client.get_diagnostics(campaign_id)
        diag_path = os.path.join(
            artifact_dir,
            f"diagnostics_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
        )
        with open(diag_path, "w") as f:
            json.dump(diag, f, indent=2, default=str)
        print(f"[EVENT] Diagnostics saved: {diag_path}")
    except Exception as e:
        print(f"[ALERT] Diagnostics failed: {e}")
        logger.error("diagnostics failed: %s", e)

    logger.info("campaign end  attempted=%d  campaign_id=%s", attempted, campaign_id)