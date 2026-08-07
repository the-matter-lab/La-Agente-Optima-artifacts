from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .oracle import DirectArylationOracle, DirectArylationOracleError

OWNER_MARKER = "akg-eval-e646b14a77fb4943a13679364402b230"
CACHE_BUSTER_NONCE = "4668867d-0d42-40e5-b6a7-fd20a6a68c0e"
CAMPAIGN_SLUG = "direct_arylation_bo"
OBJECTIVE_NAME = "yield"
OBJECTIVE_UNIT = "percent"
DEFAULT_CAMPAIGN_NAME = (
    f"direct_arylation_yield_{OWNER_MARKER}_{CACHE_BUSTER_NONCE}"
)

BASES = [
    "Potassium acetate",
    "Potassium pivalate",
    "Cesium acetate",
    "Cesium pivalate",
]
LIGANDS = [
    "BrettPhos",
    "Di-tert-butylphenylphosphine",
    "(t-Bu)PhCPhos",
    "Tricyclohexylphosphine",
    "PPh3",
    "XPhos",
    "P(2-furyl)3",
    "Methyldiphenylphosphine",
    "1268824-69-6",
    "JackiePhos",
    "SCHEMBL15068049",
    "Me2PPh",
]
SOLVENTS = ["DMAc", "Butyornitrile", "Butyl Ester", "p-Xylene"]
CONCENTRATIONS = [0.057, 0.1, 0.153]
TEMPERATURES_C = [90, 105, 120]


@dataclass(frozen=True)
class CampaignPaths:
    root: Path
    attempts_jsonl: Path
    diagnostics_json: Path
    summary_json: Path
    intake_json: Path
    campaign_json: Path
    manifest_json: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_intake(
    *,
    campaign_name: str,
    description: str,
    backend: str,
    batch_size: int,
    initial_design_size: int,
    random_seed: int,
) -> dict[str, Any]:
    return {
        "name": campaign_name,
        "description": description,
        "backend": backend,
        "batch_size": batch_size,
        "initial_design_size": initial_design_size,
        "random_seed": random_seed,
        "parameters": [
            {"name": "base", "type": "categorical", "categories": BASES},
            {"name": "ligand", "type": "categorical", "categories": LIGANDS},
            {"name": "solvent", "type": "categorical", "categories": SOLVENTS},
            {
                "name": "concentration",
                "type": "discrete",
                "values": CONCENTRATIONS,
            },
            {
                "name": "temperature_c",
                "type": "discrete",
                "values": TEMPERATURES_C,
            },
        ],
        "objectives": [
            {
                "name": OBJECTIVE_NAME,
                "direction": "maximize",
                "unit": OBJECTIVE_UNIT,
            }
        ],
    }


def artifact_paths(campaign_id: str) -> CampaignPaths:
    root = Path("artifacts") / CAMPAIGN_SLUG / campaign_id
    root.mkdir(parents=True, exist_ok=True)
    return CampaignPaths(
        root=root,
        attempts_jsonl=root / "attempts.jsonl",
        diagnostics_json=root / "diagnostics_latest.json",
        summary_json=root / "summary_latest.json",
        intake_json=root / "intake.json",
        campaign_json=root / "campaign.json",
        manifest_json=Path("campaign_manifest.json"),
    )


def update_manifest(paths: CampaignPaths) -> None:
    manifest = {
        "campaign_slug": CAMPAIGN_SLUG,
        "package_modules": [
            f"{CAMPAIGN_SLUG}.__init__",
            f"{CAMPAIGN_SLUG}.oracle",
            f"{CAMPAIGN_SLUG}.campaign",
        ],
        "run_entrypoint": "run_direct_arylation_bo.py",
        "latest_artifact_dir": str(paths.root),
    }
    paths.manifest_json.write_text(json.dumps(manifest, indent=2) + "\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def get_campaign(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    return client._json_request("GET", f"/api/v1/campaigns/{campaign_id}")


def require_owned_campaign(campaign: dict[str, Any]) -> None:
    name = campaign.get("name", "")
    if OWNER_MARKER not in name:
        raise RuntimeError(
            f"Refusing to use campaign without owner marker {OWNER_MARKER!r}: {name!r}"
        )


def ensure_campaign(
    client: BoMcpClient,
    *,
    campaign_id: str | None,
    campaign_name: str,
    description: str,
    backend: str,
    batch_size: int,
    initial_design_size: int,
    random_seed: int,
) -> tuple[str, dict[str, Any], CampaignPaths]:
    if campaign_id:
        campaign = get_campaign(client, campaign_id)
        require_owned_campaign(campaign)
        status = (campaign.get("status") or "").lower()
        if status == "paused":
            client.lifecycle(campaign_id, action="resume")
            campaign = get_campaign(client, campaign_id)
        elif status == "completed":
            client.lifecycle(campaign_id, action="reopen")
            campaign = get_campaign(client, campaign_id)
        elif status in {"created", "running"}:
            pass
        else:
            raise RuntimeError(f"Unsupported campaign status for continuation: {campaign.get('status')}")
        paths = artifact_paths(campaign_id)
        update_manifest(paths)
        return campaign_id, campaign, paths

    intake = build_intake(
        campaign_name=campaign_name,
        description=description,
        backend=backend,
        batch_size=batch_size,
        initial_design_size=initial_design_size,
        random_seed=random_seed,
    )
    validation = client.validate_intake(intake)
    if not validation.get("valid", False):
        raise RuntimeError(f"Campaign intake validation failed: {validation.get('errors', [])}")
    response = client.create_campaign(
        intake,
        idempotency_key=client.make_idempotency_key("create", campaign_name),
    )
    created_campaign_id = response["campaign_id"]
    campaign = get_campaign(client, created_campaign_id)
    require_owned_campaign(campaign)
    paths = artifact_paths(created_campaign_id)
    paths.intake_json.write_text(json.dumps(intake, indent=2) + "\n")
    paths.campaign_json.write_text(json.dumps(campaign, indent=2) + "\n")
    update_manifest(paths)
    return created_campaign_id, campaign, paths


def next_pending_suggestion(client: BoMcpClient, campaign_id: str) -> dict[str, Any] | None:
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=500)
    if pending:
        pending.sort(key=lambda row: row.get("created_at", ""))
        return pending[0]
    return None


def generate_one_suggestion(client: BoMcpClient, campaign_id: str) -> dict[str, Any]:
    response = client.generate_suggestions(campaign_id, batch_size=1)
    suggestions = response.get("suggestions") or []
    if len(suggestions) != 1:
        raise RuntimeError(f"Expected exactly one suggestion, got {len(suggestions)}")
    return suggestions[0]


def record_attempt(paths: CampaignPaths, record: dict[str, Any]) -> None:
    append_jsonl(paths.attempts_jsonl, record)


def write_summary(
    *,
    client: BoMcpClient,
    campaign_id: str,
    paths: CampaignPaths,
    invocation_attempt_budget: int,
) -> dict[str, Any]:
    attempts = load_jsonl(paths.attempts_jsonl)
    successful = [row for row in attempts if row.get("status") == "succeeded"]
    best_row = max(
        successful,
        key=lambda row: row["objective_values"][OBJECTIVE_NAME],
        default=None,
    )
    campaign = get_campaign(client, campaign_id)
    diagnostics: dict[str, Any] | None = None
    try:
        diagnostics = client.get_diagnostics(campaign_id, verbosity="standard", timeout_s=600)
        paths.diagnostics_json.write_text(json.dumps(diagnostics, indent=2) + "\n")
    except Exception as exc:  # noqa: BLE001
        diagnostics = {"warning": f"diagnostics_unavailable: {exc}"}
        paths.diagnostics_json.write_text(json.dumps(diagnostics, indent=2) + "\n")

    summary = {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name"),
        "campaign_status": campaign.get("status"),
        "attempted_evaluations": len(attempts),
        "successful_evaluations": len(successful),
        "invocation_attempt_budget": invocation_attempt_budget,
        "objective_name": OBJECTIVE_NAME,
        "objective_direction": "maximize",
        "objective_unit": OBJECTIVE_UNIT,
        "best": None
        if best_row is None
        else {
            "parameter_values": best_row["parameter_values"],
            "objective_values": best_row["objective_values"],
            "attempt_index": best_row["attempt_index"],
            "suggestion_id": best_row.get("suggestion_id"),
        },
        "attempts": attempts,
        "diagnostics": diagnostics,
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_campaign(
    *,
    campaign_id: str | None,
    invocation_attempt_budget: int,
    backend: str,
    batch_size: int,
    initial_design_size: int,
    random_seed: int,
    campaign_name: str = DEFAULT_CAMPAIGN_NAME,
    oracle_timeout_s: float = 30.0,
) -> dict[str, Any]:
    if invocation_attempt_budget < 0:
        raise ValueError("invocation_attempt_budget must be non-negative")
    if OWNER_MARKER not in campaign_name:
        raise ValueError(f"campaign_name must include owner marker {OWNER_MARKER}")

    description = (
        "Direct arylation reaction-yield optimization benchmark; "
        f"owner_marker={OWNER_MARKER}; cache_buster_nonce={CACHE_BUSTER_NONCE}; "
        "single-objective maximize yield (percent); "
        "search space: base, ligand, solvent, concentration, temperature_c; "
        "sequential batch_size=1; fully controlled oracle lookups only."
    )
    client = BoMcpClient.from_env(timeout_s=120.0)
    oracle = DirectArylationOracle(timeout_s=oracle_timeout_s)
    campaign_id, campaign, paths = ensure_campaign(
        client,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        description=description,
        backend=backend,
        batch_size=batch_size,
        initial_design_size=initial_design_size,
        random_seed=random_seed,
    )
    print(f"[optima] campaign_id={campaign_id} status={campaign.get('status')}")
    print(
        f"[optima] invocation_budget={invocation_attempt_budget} backend={backend} "
        f"initial_design_size={initial_design_size} batch_size={batch_size}"
    )

    for _ in range(invocation_attempt_budget):
        suggestion = next_pending_suggestion(client, campaign_id)
        if suggestion is None:
            decision = client.next_action(campaign_id)
            print(
                "[optima] next_action="
                f"{decision.get('action')} status={decision.get('status')} "
                f"iteration={decision.get('iteration')} n_results={decision.get('n_results')}"
            )
            if decision.get("action") != "bo_generate_suggestions":
                print(f"[optima] stopping early: {decision}")
                break
            suggestion = generate_one_suggestion(client, campaign_id)

        parameter_values = suggestion["parameter_values"]
        suggestion_id = suggestion["suggestion_id"]
        attempt_index = len(load_jsonl(paths.attempts_jsonl)) + 1
        print(
            f"[optima] attempt={attempt_index} suggestion_id={suggestion_id} "
            f"params={json.dumps(parameter_values, sort_keys=True)}"
        )
        record: dict[str, Any] = {
            "attempt_index": attempt_index,
            "timestamp_utc": utc_now_iso(),
            "campaign_id": campaign_id,
            "suggestion_id": suggestion_id,
            "parameter_values": parameter_values,
            "objective_name": OBJECTIVE_NAME,
            "objective_unit": OBJECTIVE_UNIT,
        }
        try:
            objective_values, oracle_meta = oracle.evaluate(parameter_values)
        except DirectArylationOracleError as exc:
            update_payload = None
            update_error = None
            try:
                update_payload = client.update_suggestion_status(suggestion_id, "rejected")
            except Exception as inner_exc:  # noqa: BLE001
                update_error = str(inner_exc)
            record.update(
                {
                    "status": "oracle_exception",
                    "objective_values": None,
                    "error": str(exc),
                    "suggestion_status_update": update_payload,
                    "suggestion_status_update_error": update_error,
                }
            )
            record_attempt(paths, record)
            print(f"[optima] oracle exception on attempt {attempt_index}: {exc}")
            continue

        if objective_values is None:
            update_payload = None
            update_error = None
            try:
                update_payload = client.update_suggestion_status(suggestion_id, "rejected")
            except Exception as inner_exc:  # noqa: BLE001
                update_error = str(inner_exc)
            record.update(
                {
                    "status": "oracle_http_error",
                    "objective_values": None,
                    "oracle": oracle_meta,
                    "suggestion_status_update": update_payload,
                    "suggestion_status_update_error": update_error,
                }
            )
            record_attempt(paths, record)
            print(
                f"[optima] oracle http error on attempt {attempt_index}: "
                f"status={oracle_meta.get('http_status')}"
            )
            continue

        result_row = {
            "suggestion_id": suggestion_id,
            "parameter_values": parameter_values,
            "objective_values": objective_values,
        }
        idempotency_key = client.make_idempotency_key("submit", campaign_id, suggestion_id)
        try:
            submit_response = client.submit_results(
                campaign_id,
                results=[result_row],
                idempotency_key=idempotency_key,
                force=True,
            )
            record.update(
                {
                    "status": "succeeded",
                    "objective_values": objective_values,
                    "oracle": oracle_meta,
                    "submit_response": submit_response,
                    "idempotency_key": idempotency_key,
                }
            )
            record_attempt(paths, record)
            print(
                f"[optima] submitted attempt={attempt_index} yield={objective_values[OBJECTIVE_NAME]:.2f}"
            )
        except (BoMcpClientError, BoMcpOperationError) as exc:
            update_payload = None
            update_error = None
            try:
                update_payload = client.update_suggestion_status(suggestion_id, "rejected")
            except Exception as inner_exc:  # noqa: BLE001
                update_error = str(inner_exc)
            record.update(
                {
                    "status": "submit_error",
                    "objective_values": objective_values,
                    "oracle": oracle_meta,
                    "error": str(exc),
                    "suggestion_status_update": update_payload,
                    "suggestion_status_update_error": update_error,
                    "idempotency_key": idempotency_key,
                }
            )
            record_attempt(paths, record)
            print(f"[optima] submit error on attempt {attempt_index}: {exc}")

    try:
        latest = get_campaign(client, campaign_id)
        if (latest.get("status") or "").lower() == "running":
            client.lifecycle(campaign_id, action="pause")
    except Exception as exc:  # noqa: BLE001
        print(f"[optima] warning: failed to pause campaign {campaign_id}: {exc}")

    summary = write_summary(
        client=client,
        campaign_id=campaign_id,
        paths=paths,
        invocation_attempt_budget=invocation_attempt_budget,
    )
    print(
        "[optima] summary "
        f"attempted={summary['attempted_evaluations']} successful={summary['successful_evaluations']} "
        f"best_yield={None if summary['best'] is None else summary['best']['objective_values'][OBJECTIVE_NAME]}"
    )
    return summary
