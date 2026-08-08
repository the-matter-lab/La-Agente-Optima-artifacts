"""Campaign intake construction and BO-MCP orchestration loop."""

from __future__ import annotations

import time
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from .evaluator import evaluate
from .reporting import ResultsArtifact

# ── constants ──────────────────────────────────────────────────────────
OWNERSHIP_MARKER = "akg-eval-daf20aa41d3740deb3539505c9fed77d"
CAMPAIGN_NAME = f"{OWNERSHIP_MARKER}-ackley-6d"
PARAM_NAMES = ["x_1", "x_2", "x_3", "x_4", "x_5", "x_6"]
OBJECTIVE_NAME = "surface_response"
TOTAL_BUDGET = 60


def build_intake() -> dict:
    """Return the campaign intake dict for the 6-D Ackley benchmark."""
    parameters = [
        {
            "name": name,
            "type": "continuous",
            "bounds": {"lower": 0.0, "upper": 1.0},
        }
        for name in PARAM_NAMES
    ]

    objectives = [
        {
            "name": OBJECTIVE_NAME,
            "direction": "maximize",
            "unit": "normalized_unitless",
        }
    ]

    return {
        "name": CAMPAIGN_NAME,
        "description": "6-D Ackley synthetic benchmark (baybe backend)",
        "backend": "baybe",
        "parameters": parameters,
        "objectives": objectives,
        "batch_size": 1,
        "initial_design_size": 12,
        "acquisition_method": "expected_improvement",
        "random_seed": 2024,
    }


def _tagged(tag: str, msg: str) -> None:
    """Print a tagged line (unbuffered)."""
    print(f"[{tag}] {msg}", flush=True)


def run_loop(
    campaign_id: str,
    client: BoMcpClient,
    artifact: ResultsArtifact,
    max_evals: int = TOTAL_BUDGET,
    poll_s: float = 180.0,
    heartbeat_s: float = 1800.0,
    stop_file: str | None = None,
) -> None:
    """Execute the BO loop until *max_evals* successful evaluations or stop."""

    n_attempted = artifact.n_attempted()
    n_success = artifact.n_success()
    last_heartbeat = time.monotonic()

    while n_attempted < max_evals:
        # ── stop-file check ────────────────────────────────────────
        if stop_file and Path(stop_file).exists():
            _tagged("EVENT", f"Stop file detected ({stop_file}); pausing campaign")
            Path(stop_file).unlink(missing_ok=True)
            # Pause only if campaign is still running
            try:
                info = client.get_campaign(campaign_id)
                if info.get("status") == "running":
                    client.lifecycle(campaign_id, action="pause")
                    _tagged("EVENT", "Campaign paused")
            except Exception:
                pass
            break

        # ── heartbeat ──────────────────────────────────────────────
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_s:
            _tagged("HEARTBEAT", f"attempted={n_attempted} success={n_success} budget={max_evals}")
            last_heartbeat = now

        # ── ask server what to do next ─────────────────────────────
        try:
            decision = client.next_action(campaign_id)
        except Exception as exc:
            _tagged("ALERT", f"next_action failed: {exc}")
            time.sleep(min(poll_s, 30))
            continue

        action = decision.get("action", "")
        if action != "bo_generate_suggestions":
            _tagged("EVENT", f"Server action={action}; stopping loop")
            break

        # ── generate suggestion ────────────────────────────────────
        try:
            gen = client.generate_suggestions(campaign_id, batch_size=1)
        except Exception as exc:
            _tagged("ALERT", f"Suggestion generation failed: {exc}")
            time.sleep(min(poll_s, 30))
            continue

        if not gen.get("success", False):
            errors = gen.get("errors", [])
            _tagged("ALERT", f"Suggestion generation unsuccessful: {errors}")
            break

        suggestions = gen.get("suggestions", [])
        if not suggestions:
            _tagged("ALERT", "No suggestions returned")
            break

        sug = suggestions[0]
        suggestion_id = sug["suggestion_id"]
        param_values = sug["parameter_values"]

        # ── parse coordinates early ─────────────────────────────────
        try:
            coords = {k: float(param_values[k]) for k in PARAM_NAMES}
        except Exception as exc:
            _tagged("ALERT", f"Could not parse suggestion params: {exc}")
            try:
                client.update_suggestion_status(suggestion_id, status="rejected")
            except Exception:
                pass
            continue

        # ── duplicate-point check ───────────────────────────────────
        if artifact.has_coords(coords):
            _tagged("EVENT", f"Duplicate point detected; rejecting suggestion {suggestion_id}")
            try:
                client.update_suggestion_status(suggestion_id, status="rejected")
            except Exception:
                pass
            continue  # do NOT count as attempted evaluation



        # ── evaluate ───────────────────────────────────────────────
        n_attempted += 1
        eval_idx = n_attempted

        try:
            result = evaluate(**coords)
            raw_response = result["raw_response"]
            surface_response = result["surface_response"]
            status = "success"
            failure_reason = ""
        except Exception as exc:
            raw_response = None
            surface_response = None
            status = "failed"
            failure_reason = str(exc)
            _tagged("ALERT", f"Evaluation {eval_idx} failed: {exc}")

        # ── submit result ──────────────────────────────────────────
        if status == "success":
            result_row = {
                "parameter_values": coords,
                "objective_values": {OBJECTIVE_NAME: surface_response},
                "suggestion_id": suggestion_id,
                "metadata": {
                    "conditions": {"raw_response": raw_response},
                },
            }
            idem_key = BoMcpClient.make_idempotency_key("result", campaign_id, str(eval_idx))
            try:
                submit_resp = client.submit_results(
                    campaign_id,
                    results=[result_row],
                    idempotency_key=idem_key,
                )
                if not submit_resp.get("success", False):
                    sub_errors = submit_resp.get("errors", [])
                    _tagged("ALERT", f"Result submission rejected: {sub_errors}")
                    # Still record locally as attempted
            except Exception as exc:
                _tagged("ALERT", f"Result submission exception: {exc}")

            n_success += 1
            _tagged("RESULT",
                     f"eval={eval_idx} surface_response={surface_response:.6f} "
                     f"raw_response={raw_response:.6f} "
                     + " ".join(f"{k}={v:.4f}" for k, v in coords.items()))
        else:
            # Reject the suggestion so the server knows it wasn't evaluated
            try:
                client.update_suggestion_status(suggestion_id, status="rejected")
            except Exception:
                pass

        # ── persist to artifact ────────────────────────────────────
        artifact.append(
            evaluation_index=eval_idx,
            parameter_values=coords if status == "success" else {k: param_values.get(k) for k in PARAM_NAMES},
            objective_values={OBJECTIVE_NAME: surface_response} if status == "success" else {},
            status=status,
            failure_reason=failure_reason,
            raw_response=raw_response,
        )

        # ── budget check ───────────────────────────────────────────
        if n_attempted >= max_evals:
            _tagged("EVENT", f"Budget reached: {n_attempted}/{max_evals}")
            break

        time.sleep(0.1)  # small pacing

    # ── end-of-loop summary ────────────────────────────────────────
    _tagged("EVENT", f"Loop finished: attempted={n_attempted} success={n_success}")
    artifact.finalize()

    # Print best
    best = artifact.best()
    if best:
        best_sr = best["objective_values"].get("surface_response", float("nan"))
        best_rr = best.get("raw_response", float("nan"))
        _tagged("RESULT",
                 f"BEST surface_response={best_sr:.6f} "
                 f"raw_response={best_rr:.6f} "
                 + " ".join(f"{k}={v:.6f}" for k, v in best["parameter_values"].items()))
