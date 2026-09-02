from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import logfire
from domains.bo_mcp.client import BoMcpClient

from .history import audit_rows, load_seed_results
from .intake import build_intake

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPORT = ROOT / "artifacts/recreated_robochemflex_yield_bo_20260725/failed_measurement_retry_continuation_20260726T184638Z/bo_campaign_export.csv"


def run(args: argparse.Namespace) -> None:
    export_csv = _resolve(args.source_export)
    artifact_dir = _artifact_dir(args.artifact_dir, "yield_only_recreation_preflight" if args.dry_run else "yield_only_recreation")
    artifact_dir.mkdir(parents=True, exist_ok=False)

    intake = build_intake(args.campaign_name or f"robochemflex_yield_only_recreated_{_stamp()}")
    results = load_seed_results(export_csv, expected_count=args.expected_seed_count)
    _write_json(artifact_dir / "yield_only_intake.json", intake)
    _write_json(artifact_dir / "yield_only_seed_results.json", results)
    _write_json(artifact_dir / "source_export_rows.audit.json", audit_rows(export_csv))
    _write_json(
        artifact_dir / "preflight_summary.json",
        {
            "source_export": str(export_csv.relative_to(ROOT) if export_csv.is_relative_to(ROOT) else export_csv),
            "seed_result_count": len(results),
            "objective_names": [o["name"] for o in intake["objectives"]],
            "has_green_objective": any(o["name"] == "green_score" for o in intake["objectives"]),
            "has_scalarization": bool(intake.get("scalarization") or intake.get("scalarizer")),
            "will_contact_roboflex": False,
            "will_create_or_submit_bo": (not args.dry_run),
            "operator_confirmation_required": True,
        },
    )

    print(f"Prepared yield-only intake and {len(results)} seed result(s).")
    print("RoboFlex/hardware calls: none.")
    print(f"Artifacts: {artifact_dir}")

    if args.validate_intake:
        client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
        response = client.validate_intake(intake)
        _write_json(artifact_dir / "bo_validate_intake_response.json", response)
        print(f"BO-MCP intake validation: valid={response.get('valid')}")

    if args.dry_run:
        print("Dry-run/preflight only; no campaign was created and no seed rows were submitted.")
        return

    if not args.confirm_create_seed:
        raise SystemExit("Refusing BO-MCP create/seed without --confirm-create-seed")

    client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    validate = client.validate_intake(intake)
    _write_json(artifact_dir / "bo_validate_intake_response.json", validate)
    campaign_id = args.campaign_id or _create_campaign(client, intake, args.run_nonce)
    (artifact_dir / "bo_campaign_id.txt").write_text(campaign_id + "\n")
    print(f"Created/using yield-only BO-MCP campaign: {campaign_id}")

    existing = client.get_results(campaign_id)
    submitted = 0
    skipped = 0
    for index, result in enumerate(results, start=1):
        if _coordinate_exists(existing, result["parameter_values"]):
            skipped += 1
            _append_json(artifact_dir / "seed_audit.jsonl", {"source_row": index, "action": "skipped_existing_coordinate"})
            continue
        key = BoMcpClient.make_idempotency_key("yield-only-seed", campaign_id, str(index), _run_nonce(args.run_nonce))
        response = client.submit_results(campaign_id, results=[result], idempotency_key=key, force=False)
        submitted += len(response.get("result_ids", []))
        existing = client.get_results(campaign_id)
        _append_json(artifact_dir / "seed_audit.jsonl", {"source_row": index, "action": "submitted", "response": response})
        print(f"Seeded row {index:02d}")

    final_results = client.get_results(campaign_id)
    _write_json(artifact_dir / "final_bomcp_results.json", final_results)
    _export_and_pause(client, campaign_id, artifact_dir)
    _write_json(
        artifact_dir / "recreation_summary.json",
        {"campaign_id": campaign_id, "submitted_count": submitted, "skipped_existing_count": skipped, "final_result_count": len(final_results), "contacted_roboflex": False},
    )
    print(f"Done: submitted={submitted}, skipped_existing={skipped}, final_results={len(final_results)}")
    print(f"New yield-only campaign_id: {campaign_id}")


def _create_campaign(client: BoMcpClient, intake: dict, run_nonce: str | None) -> str:
    key = BoMcpClient.make_idempotency_key("yield-only-campaign", intake["name"], _run_nonce(run_nonce))
    return client.create_campaign(intake, idempotency_key=key)["campaign_id"]


def _coordinate_exists(existing: list[dict], candidate: dict) -> bool:
    return any(_same_coordinate(row.get("parameter_values", {}), candidate) for row in existing)


def _same_coordinate(left: dict, right: dict) -> bool:
    if set(left) != set(right):
        return False
    for key, rval in right.items():
        lval = left[key]
        if isinstance(rval, float):
            if abs(float(lval) - rval) > 1e-8:
                return False
        elif lval != rval:
            return False
    return True


def _export_and_pause(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
        (artifact_dir / "bo_campaign_export.csv").write_bytes(content)
        (artifact_dir / "bo_campaign_export.content_type.txt").write_text(content_type + "\n")
    except Exception as exc:
        print(f"Export skipped: {exc}")
    try:
        if client.get_campaign(campaign_id).get("status") == "running":
            client.lifecycle(campaign_id, action="pause")
            print("BO campaign paused after seed import.")
    except Exception as exc:
        print(f"Pause skipped: {exc}")


def _artifact_dir(path: Path | None, prefix: str) -> Path:
    return path or ROOT / "artifacts" / f"{prefix}_{_stamp()}"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _run_nonce(value: str | None) -> str:
    return value or os.environ.get("YIELD_ONLY_RUN_NONCE") or uuid4().hex[:10]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, payload) -> None:
    with path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
