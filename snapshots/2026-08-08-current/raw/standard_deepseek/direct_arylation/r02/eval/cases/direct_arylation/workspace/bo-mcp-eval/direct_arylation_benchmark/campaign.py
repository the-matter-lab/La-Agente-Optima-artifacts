"""Campaign orchestrator for the direct-arylation benchmark.

Owns the BO-MCP loop: create → (next_action → generate → evaluate →
submit) × N → pause.  Campaign-agnostic: does NOT import
campaign-specific modules so continuations can reuse it unchanged.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable

from domains.bo_mcp.client import BoMcpClient, BoMcpOperationError


def _tagged_print(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


def run_campaign(
    *,
    client: BoMcpClient,
    intake: dict[str, Any],
    campaign_id: str | None,
    evaluate_fn: Callable[[dict[str, Any]], dict[str, Any]],
    on_result: Callable[[dict[str, Any]], None],
    max_attempts: int,
    poll_s: int,
    heartbeat_s: int,
    stop_file: str,
) -> str:
    """Execute the BO-MCP campaign loop.

    Parameters
    ----------
    client : BoMcpClient
    intake : campaign intake dict (used only for creation).
    campaign_id : existing id to resume, or None to create.
    evaluate_fn : callable(candidate_dict) → {"status": "success"/"failed", "yield": ...}
    on_result : callable(result_dict) — called after each evaluation+submission.
        Receives a dict with keys: iteration, suggestion_id, candidate params,
        status, yield, submit_ok.
    max_attempts : hard cap on oracle calls for this invocation.
    poll_s : seconds between iterations.
    heartbeat_s : seconds between heartbeat lines.
    stop_file : path to a stop-marker file; checked before each generation.

    Returns
    -------
    campaign_id : str
    """
    # ── create or resume ────────────────────────────────────────────
    if campaign_id is None:
        idem_key = BoMcpClient.make_idempotency_key("da-create")
        resp = client.create_campaign(intake, idempotency_key=idem_key)
        if not resp.get("success"):
            raise BoMcpOperationError(
                f"Campaign creation rejected: {resp.get('errors')}", resp
            )
        campaign_id = resp["campaign_id"]
        _tagged_print("EVENT", f"Created campaign {campaign_id}")
    else:
        status_info = client.next_action(campaign_id)
        current_status = status_info.get("status", "unknown")
        _tagged_print("EVENT", f"Resuming campaign {campaign_id} (status={current_status})")
        if current_status == "paused":
            client.lifecycle(campaign_id, action="resume")
            _tagged_print("EVENT", "Resumed paused campaign")
        elif current_status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            _tagged_print("EVENT", "Reopened completed campaign")

    # ── main loop ───────────────────────────────────────────────────
    last_heartbeat = time.monotonic()
    attempt = 0

    while attempt < max_attempts:
        # --- stop-file check (before generating) ---
        if os.path.exists(stop_file):
            _tagged_print("EVENT", f"Stop file '{stop_file}' detected — shutting down")
            os.remove(stop_file)
            break

        # --- heartbeat ---
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _tagged_print("HEARTBEAT", f"Alive — {attempt}/{max_attempts} attempts used")
            last_heartbeat = now

        # --- next action ---
        try:
            decision = client.next_action(campaign_id)
        except BoMcpOperationError as exc:
            _tagged_print("ALERT", f"next_action failed: {exc}")
            time.sleep(poll_s)
            continue

        action = decision.get("action")
        _tagged_print(
            "EVENT",
            f"Iter {decision.get('iteration')}  results={decision.get('n_results')}  "
            f"action={action}  reason={decision.get('reason')}",
        )

        if action != "bo_generate_suggestions":
            _tagged_print("EVENT", f"Server says stop: {decision.get('reason')}")
            break

        # --- generate suggestion ---
        try:
            gen = client.generate_suggestions(campaign_id, batch_size=1)
        except BoMcpOperationError as exc:
            _tagged_print("ALERT", f"generate_suggestions rejected: {exc}")
            time.sleep(poll_s)
            continue

        if not gen.get("success") or not gen.get("suggestions"):
            _tagged_print("ALERT", f"No suggestions: {gen.get('errors')}")
            time.sleep(poll_s)
            continue

        suggestion = gen["suggestions"][0]
        suggestion_id = suggestion["suggestion_id"]
        params = suggestion["parameter_values"]
        iteration = gen.get("iteration")

        _tagged_print(
            "EVENT",
            f"Suggestion {suggestion_id}: "
            + " | ".join(f"{k}={v!r}" for k, v in params.items()),
        )

        # --- evaluate ---
        attempt += 1
        eval_result = evaluate_fn(params)

        submit_ok = False
        if eval_result["status"] == "success":
            yield_val = eval_result["yield"]
            _tagged_print("RESULT", f"Attempt {attempt}/{max_attempts}  yield={yield_val:.2f}%")

            result_row = {
                "parameter_values": params,
                "objective_values": {"yield": yield_val},
                "suggestion_id": suggestion_id,
            }
            idem_key = BoMcpClient.make_idempotency_key("da-submit", campaign_id, suggestion_id)
            try:
                client.submit_results(
                    campaign_id,
                    results=[result_row],
                    idempotency_key=idem_key,
                )
                submit_ok = True
            except BoMcpOperationError as exc:
                _tagged_print("ALERT", f"submit_results rejected: {exc}")
        else:
            _tagged_print(
                "ALERT",
                f"Attempt {attempt}/{max_attempts}  FAILED  "
                f"http={eval_result.get('http_status')}  "
                f"detail={eval_result.get('detail', '')[:200]}",
            )
            # Reject the suggestion so BO-MCP knows it wasn't evaluated.
            try:
                client.update_suggestion_status(suggestion_id, "rejected")
            except BoMcpOperationError:
                pass

        # --- notify caller ---
        on_result(
            {
                "iteration": iteration,
                "suggestion_id": suggestion_id,
                "candidate": params,
                "status": eval_result["status"],
                "yield": eval_result.get("yield"),
                "submit_ok": submit_ok,
            }
        )

        # --- poll delay ---
        time.sleep(poll_s)

    # ── shutdown: pause (not terminate) so resume works ─────────────
    try:
        decision = client.next_action(campaign_id)
        if decision.get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            _tagged_print("EVENT", "Campaign paused for later resume")
    except BoMcpOperationError:
        _tagged_print("ALERT", "Could not pause campaign — check status manually")

    return campaign_id