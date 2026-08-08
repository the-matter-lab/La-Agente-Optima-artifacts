import os
import json
import logging
from typing import Any
from domains.direct_arylation.client import (
    evaluate_direct_arylation,
    DirectArylationClientError,
)
from domains.bo_mcp.client import BoMcpClient

logger = logging.getLogger(__name__)

ARTIFACT_PATH = "direct_arylation_attempts.json"


def load_attempts() -> list[dict[str, Any]]:
    """Load existing attempts from the local JSON artifact."""
    if os.path.exists(ARTIFACT_PATH):
        try:
            with open(ARTIFACT_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load attempts from {ARTIFACT_PATH}: {e}")
    return []


def save_attempts(attempts: list[dict[str, Any]]) -> None:
    """Save the list of attempts to the local JSON artifact."""
    try:
        with open(ARTIFACT_PATH, "w") as f:
            json.dump(attempts, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save attempts to {ARTIFACT_PATH}: {e}")


def sync_attempts_from_server(client: BoMcpClient, campaign_id: str) -> list[dict[str, Any]]:
    """Synchronize the local attempts artifact with the server's suggestions and results."""
    logger.info(f"Synchronizing attempts from server for campaign {campaign_id}...")
    try:
        suggestions = client.query_suggestions(campaign_id)
        results = client.get_results(campaign_id)
    except Exception as e:
        logger.error(f"Failed to fetch suggestions or results from server: {e}")
        return load_attempts()

    # Map suggestion_id to result for completed suggestions
    results_map = {r["suggestion_id"]: r for r in results if r.get("suggestion_id")}

    reconstructed_attempts = []
    for s in suggestions:
        status = s.get("status")
        if status not in ("completed", "rejected"):
            continue

        # Standardize parameter values
        params = s.get("parameter_values") or {}
        base = str(params.get("base"))
        ligand = str(params.get("ligand"))
        solvent = str(params.get("solvent"))
        concentration = float(params.get("concentration"))
        temperature_c = int(float(params.get("temperature_c")))

        standardized_params = {
            "base": base,
            "ligand": ligand,
            "solvent": solvent,
            "concentration": concentration,
            "temperature_c": temperature_c
        }

        record = {
            "parameter_values": standardized_params,
        }

        if status == "completed":
            record["status"] = "success"
            s_id = s.get("suggestion_id")
            res = results_map.get(s_id)
            if res and "objective_values" in res:
                record["objective_values"] = res["objective_values"]
            else:
                record["objective_values"] = {"yield": 0.0}
        else:  # rejected
            record["status"] = "failed"
            record["error_message"] = "Evaluation failed (rejected suggestion)"

        reconstructed_attempts.append(record)

    save_attempts(reconstructed_attempts)
    return reconstructed_attempts

def evaluate_candidate(parameter_values: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single candidate against the direct arylation oracle.

    Returns a dict representing the attempt record.
    """
    # Standardize parameter values
    base = str(parameter_values.get("base"))
    ligand = str(parameter_values.get("ligand"))
    solvent = str(parameter_values.get("solvent"))
    concentration = float(parameter_values.get("concentration"))
    temperature_c = int(float(parameter_values.get("temperature_c")))

    standardized_params = {
        "base": base,
        "ligand": ligand,
        "solvent": solvent,
        "concentration": concentration,
        "temperature_c": temperature_c,
    }

    record: dict[str, Any] = {
        "parameter_values": standardized_params,
        "status": "failed",
    }

    try:
        # Call the oracle
        measured_yield = evaluate_direct_arylation(
            base=base,
            ligand=ligand,
            solvent=solvent,
            concentration=concentration,
            temperature_c=temperature_c,
        )
        record["status"] = "success"
        record["objective_values"] = {"yield": measured_yield}
        print(
            f"[RESULT] Evaluated candidate: {standardized_params} -> yield: {measured_yield}%"
        )
    except DirectArylationClientError as e:
        record["error_message"] = str(e)
        print(
            f"[ALERT] Oracle evaluation failed for candidate {standardized_params}: {e}"
        )
    except Exception as e:
        record["error_message"] = f"Unexpected error: {e}"
        print(
            f"[ALERT] Unexpected error evaluating candidate {standardized_params}: {e}"
        )

    # Save to local JSON artifact
    attempts = load_attempts()
    attempts.append(record)
    save_attempts(attempts)

    return record
