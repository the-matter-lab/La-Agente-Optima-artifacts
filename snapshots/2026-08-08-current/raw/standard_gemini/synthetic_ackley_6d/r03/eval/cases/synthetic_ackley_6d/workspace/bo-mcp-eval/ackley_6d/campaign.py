# ackley_6d/campaign.py
# Cache-buster nonce: 54354cdc-4da6-4419-86a6-f4560fc0efbe

import json
import os
import sys
import time
from typing import Optional

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError
from .evaluator import evaluate_ackley_6d
from .intake import get_intake
from .reporting import print_final_report, save_results_artifact

OWNERSHIP_MARKER = "akg-eval-43dcff3d628d4a86ba717e0455386a93"
NONCE = "54354cdc-4da6-4419-86a6-f4560fc0efbe"
BUDGET = 60


def _point_key(parameter_values: dict) -> tuple:
    return tuple(round(float(parameter_values[f"x_{i}"]), 12) for i in range(1, 7))


def _reconstruct_history(client: BoMcpClient, campaign_id: str) -> list[dict]:
    server_results = client.get_results(campaign_id)
    all_suggestions = client.query_suggestions(campaign_id, limit=500)
    results_by_suggestion_id = {
        row.get("suggestion_id"): row for row in server_results if row.get("suggestion_id")
    }

    history = []
    for idx, suggestion in enumerate(all_suggestions, start=1):
        suggestion_id = suggestion["suggestion_id"]
        parameter_values = suggestion["parameter_values"]
        if suggestion_id in results_by_suggestion_id:
            _, eval_results, _ = evaluate_ackley_6d(parameter_values)
            history.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": parameter_values,
                    "objective_values": {
                        "surface_response": results_by_suggestion_id[suggestion_id]["objective_values"]["surface_response"]
                    },
                    "status": "success",
                    "failure_reason": "",
                    "raw_response": eval_results.get("raw_response"),
                }
            )
        elif suggestion.get("status") == "rejected":
            history.append(
                {
                    "evaluation_index": idx,
                    "parameter_values": parameter_values,
                    "objective_values": {},
                    "status": "failed",
                    "failure_reason": "Rejected / evaluation failed before result submission",
                    "raw_response": None,
                }
            )
    return history


def _save_history_jsonl(json_path: str, history: list[dict]) -> None:
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)


def run_campaign(
    campaign_id: Optional[str] = None,
    campaign_name: str = "Ackley 6D Optimization",
    random_seed: int = 20260730,
    initial_design_size: int = 12,
    backend: str = "botorch",
    poll_s: int = 0,
    heartbeat_s: int = 30,
    stop_file: str = "STOP",
    artifact_dir: str = "artifacts",
    max_evaluations: Optional[int] = None,
):
    client = BoMcpClient.from_env()
    os.makedirs(artifact_dir, exist_ok=True)
    results_path = os.path.join(artifact_dir, "results_history.json")

    invocation_budget = BUDGET if max_evaluations is None else min(int(max_evaluations), BUDGET)

    if campaign_id:
        print(f"[EVENT] Resuming existing campaign: {campaign_id}")
        campaign = client.get_campaign(campaign_id)
        name = campaign.get("name", "")
        if OWNERSHIP_MARKER not in name:
            print(
                f"[ALERT] Refusing to resume campaign without ownership marker {OWNERSHIP_MARKER}: {name}"
            )
            sys.exit(1)
        status = campaign.get("status")
        if status == "paused":
            print(f"[EVENT] Campaign is paused; resuming on server.")
            client.lifecycle(campaign_id, action="resume")
        elif status == "completed":
            print(f"[EVENT] Campaign is completed; reopening on server.")
            client.lifecycle(campaign_id, action="reopen")
    else:
        full_name = f"{campaign_name} - {OWNERSHIP_MARKER}"
        print(f"[EVENT] Creating new campaign: {full_name}")
        intake = get_intake(
            full_name,
            random_seed=random_seed,
            initial_design_size=initial_design_size,
            backend=backend,
        )
        validation = client.validate_intake(intake)
        if not validation.get("valid", False):
            print(f"[ALERT] Intake validation failed: {validation}")
            sys.exit(1)
        response = client.create_campaign(
            intake,
            idempotency_key=client.make_idempotency_key("create", full_name, NONCE),
        )
        campaign_id = response["campaign_id"]
        print(f"[EVENT] Campaign created successfully. ID: {campaign_id}")

    print(f"[EVENT] Campaign ID: {campaign_id}")
    print(
        "[EVENT] Chosen settings: backend=botorch, acquisition=expected_improvement_nonlog, "
        "initialization=Sobol warm start, initial_design_size=12, batch_schedule=sequential(1), "
        "random_seed=20260730"
    )
    sys.stdout.flush()

    last_heartbeat = 0.0

    while True:
        if os.path.exists(stop_file):
            print(f"[EVENT] Stop file {stop_file!r} detected. Pausing campaign and exiting.")
            try:
                os.remove(stop_file)
            except OSError:
                pass
            client.lifecycle(campaign_id, action="pause")
            print("[EVENT] Campaign paused on server.")
            break

        history = _reconstruct_history(client, campaign_id)
        attempted_evaluations = len(history)
        successful_evaluations = sum(1 for row in history if row["status"] == "success")
        _save_history_jsonl(results_path, history)

        if attempted_evaluations >= BUDGET:
            print(f"[EVENT] Budget of {BUDGET} attempted evaluations reached.")
            break
        if attempted_evaluations >= invocation_budget:
            print(
                f"[EVENT] Invocation budget of {invocation_budget} attempted evaluations reached. Pausing campaign."
            )
            client.lifecycle(campaign_id, action="pause")
            print("[EVENT] Campaign paused on server.")
            break

        now = time.time()
        if now - last_heartbeat >= heartbeat_s:
            print(
                f"[HEARTBEAT] campaign_id={campaign_id} attempted={attempted_evaluations}/{BUDGET} success={successful_evaluations} nonce={NONCE}"
            )
            sys.stdout.flush()
            last_heartbeat = now

        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            print(
                f"[EVENT] Server recommended action={decision.get(action)} reason={decision.get(reason)} status={decision.get(status)}"
            )
            break

        all_suggestions = client.query_suggestions(campaign_id, limit=500)
        pending = [row for row in all_suggestions if row.get("status") == "pending"]
        if pending:
            suggestion = pending[0]
            print(f"[EVENT] Reusing pending suggestion {suggestion[suggestion_id]}")
        else:
            print(f"[EVENT] Generating new suggestion for evaluation {attempted_evaluations + 1}/{BUDGET}")
            generated = client.generate_suggestions(campaign_id, batch_size=1)
            if not generated.get("suggestions"):
                print(f"[ALERT] No suggestions returned: {generated}")
                time.sleep(max(poll_s, 0))
                continue
            suggestion = generated["suggestions"][0]

        suggestion_id = suggestion["suggestion_id"]
        parameter_values = suggestion["parameter_values"]
        candidate_key = _point_key(parameter_values)

        duplicate_of = None
        for prior in all_suggestions:
            if prior["suggestion_id"] == suggestion_id:
                continue
            if _point_key(prior["parameter_values"]) == candidate_key and prior.get("status") in {
                "completed",
                "pending",
                "rejected",
            }:
                duplicate_of = prior["suggestion_id"]
                break

        if duplicate_of is not None:
            print(
                f"[ALERT] Duplicate suggestion detected for {suggestion_id}; matches prior suggestion {duplicate_of}. Rejecting without evaluation."
            )
            client.update_suggestion_status(suggestion_id, "rejected")
            time.sleep(max(poll_s, 0))
            continue

        print(f"[EVENT] Evaluating {suggestion_id} parameters={parameter_values}")
        success, values, failure_reason = evaluate_ackley_6d(parameter_values)
        if success:
            result_row = {
                "suggestion_id": suggestion_id,
                "parameter_values": parameter_values,
                "objective_values": {"surface_response": values["surface_response"]},
            }
            client.submit_results(
                campaign_id,
                results=[result_row],
                idempotency_key=client.make_idempotency_key("submit", suggestion_id, NONCE),
            )
            print(
                f"[RESULT] evaluation={attempted_evaluations + 1} suggestion_id={suggestion_id} raw_response={values['raw_response']:.12f} surface_response={values['surface_response']:.12f}"
            )
        else:
            print(f"[ALERT] Evaluation failed for {suggestion_id}: {failure_reason}")
            client.update_suggestion_status(suggestion_id, "rejected")

        sys.stdout.flush()
        time.sleep(max(poll_s, 0))

    final_history = _reconstruct_history(client, campaign_id)
    save_results_artifact(results_path, final_history)
    print(f"[EVENT] Saved results history to {results_path}")
    print_final_report(campaign_id, final_history)

