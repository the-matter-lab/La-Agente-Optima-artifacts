from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from domains.bo_mcp.client import BoMcpClient

from .history import audit_rows, load_seed_results
from .intake import build_intake
from .recreate import DEFAULT_EXPORT, _coordinate_exists, _export_and_pause

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RETAINED_MEASUREMENT = ROOT / "artifacts/yield_only_robochemflex_bo/continuation_20260727T014003Z/measurement21_attempt1/bo_result_payload.json"
DEFAULT_SCAN_ROOT = ROOT / "artifacts/yield_only_robochemflex_bo"
CUTOFF_RUN_ID = "R0068"
RETAINED_RUN_ID = "R0067"
RETAINED_SAMPLE_NAME = "bo_cc26e7f1-b"
RETAINED_YIELD = 58.811245


def run(args: argparse.Namespace) -> None:
    artifact_dir = _artifact_dir(args.artifact_dir, "yield_only_clean21_recreation_preflight" if args.dry_run else "yield_only_clean21_recreation")
    artifact_dir.mkdir(parents=True, exist_ok=False)

    historical = load_seed_results(_resolve(args.source_export), expected_count=args.expected_historical_count)
    retained = _load_retained_measurement(_resolve(args.retained_measurement_payload))
    results = _strip_stale_suggestion_ids(historical + [retained])
    _assert_seed_set(results, args.expected_total_seed_count)

    intake = build_intake(args.campaign_name or f"robochemflex_yield_only_clean21_{_stamp()}")
    discard_audit = _discard_audit(_resolve(args.scan_root), results)
    _write_json(artifact_dir / "yield_only_intake.json", intake)
    _write_json(artifact_dir / "clean_seed_results.json", results)
    _write_json(artifact_dir / "source_export_rows.audit.json", audit_rows(_resolve(args.source_export)))
    _write_json(artifact_dir / "discard_audit.json", discard_audit)
    _write_json(
        artifact_dir / "preflight_summary.json",
        {
            "cutoff_run_id": CUTOFF_RUN_ID,
            "policy": "retain original 20 historical rows plus R0067 only; discard R0068 and later",
            "seed_result_count": len(results),
            "retained_run_ids": _run_ids(results),
            "excluded_run_ids_observed_in_artifacts": discard_audit["excluded_run_ids"],
            "will_contact_roboflex": False,
            "will_create_or_submit_bo": not args.dry_run,
        },
    )

    print(f"Prepared clean yield-only intake and {len(results)} seed result(s).")
    print(f"Retained RoboFlex run ids: {_run_ids(results)}")
    print(f"Excluded observed run ids >= {CUTOFF_RUN_ID}: {discard_audit['excluded_run_ids']}")
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
    print(f"Created/using clean yield-only BO-MCP campaign: {campaign_id}")

    existing = client.get_results(campaign_id)
    submitted = 0
    skipped = 0
    for index, result in enumerate(results, start=1):
        if _coordinate_exists(existing, result["parameter_values"]):
            skipped += 1
            _append_json(artifact_dir / "seed_audit.jsonl", {"source_row": index, "action": "skipped_existing_coordinate"})
            continue
        key = BoMcpClient.make_idempotency_key("yield-only-clean21-seed", campaign_id, str(index), _run_nonce(args.run_nonce))
        response = client.submit_results(campaign_id, results=[result], idempotency_key=key, force=False)
        submitted += len(response.get("result_ids", []))
        existing = client.get_results(campaign_id)
        _append_json(artifact_dir / "seed_audit.jsonl", {"source_row": index, "action": "submitted", "response": response})
        print(f"Seeded clean row {index:02d}")

    final_results = client.get_results(campaign_id)
    _write_json(artifact_dir / "final_bomcp_results.json", final_results)
    _export_and_pause(client, campaign_id, artifact_dir)
    _write_json(
        artifact_dir / "recreation_summary.json",
        {
            "campaign_id": campaign_id,
            "submitted_count": submitted,
            "skipped_existing_count": skipped,
            "final_result_count": len(final_results),
            "discard_policy": f"excluded {CUTOFF_RUN_ID}+",
            "contacted_roboflex": False,
        },
    )
    if len(final_results) != args.expected_total_seed_count:
        raise SystemExit(f"Expected {args.expected_total_seed_count} clean seed results after import; found {len(final_results)}")
    print(f"Done: submitted={submitted}, skipped_existing={skipped}, final_results={len(final_results)}")
    print(f"New clean yield-only campaign_id: {campaign_id}")


def _load_retained_measurement(path: Path) -> dict:
    payload = json.loads(path.read_text())
    run_id = (((payload.get("metadata") or {}).get("external_ref") or {}).get("id"))
    sample = (((payload.get("metadata") or {}).get("conditions") or {}).get("sample_name"))
    y = float((payload.get("objective_values") or {}).get("yield_percent", float("nan")))
    if run_id != RETAINED_RUN_ID:
        raise SystemExit(f"Retained measurement must be {RETAINED_RUN_ID}; found {run_id!r}")
    if sample != RETAINED_SAMPLE_NAME:
        raise SystemExit(f"Retained sample must be {RETAINED_SAMPLE_NAME}; found {sample!r}")
    if not math.isfinite(y) or abs(y - RETAINED_YIELD) > 0.01:
        raise SystemExit(f"Retained {RETAINED_RUN_ID} yield mismatch: {y}")
    result = {
        "parameter_values": payload["parameter_values"],
        "objective_values": {"yield_percent": y},
        "metadata": {
            "external_ref": {"system": "roboflex", "id": RETAINED_RUN_ID},
            "notes": "retained clean yield-only measurement #21 from R0067; later questionable runs discarded by operator instruction",
            "conditions": {
                "sample_name": sample,
                "prior_yield_only_campaign_id": "1970655b-a702-4963-874b-6973489cc89d",
                "prior_suggestion_id": payload.get("suggestion_id"),
                "source_payload": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            },
        },
    }
    _assert_no_forbidden_run_ids([result])
    return result


def _strip_stale_suggestion_ids(results: list[dict]) -> list[dict]:
    stripped = []
    for row in results:
        clean = json.loads(json.dumps(row))
        prior_sid = clean.pop("suggestion_id", None)
        if prior_sid:
            clean.setdefault("metadata", {}).setdefault("conditions", {}).setdefault("prior_suggestion_id", prior_sid)
        stripped.append(clean)
    return stripped


def _assert_seed_set(results: list[dict], expected_total: int) -> None:
    if len(results) != expected_total:
        raise SystemExit(f"Expected {expected_total} clean seed rows; assembled {len(results)}")
    _assert_no_forbidden_run_ids(results)
    run_ids = _run_ids(results)
    if run_ids != [RETAINED_RUN_ID]:
        raise SystemExit(f"Expected only retained RoboFlex run id {[RETAINED_RUN_ID]}; found {run_ids}")


def _assert_no_forbidden_run_ids(results: list[dict]) -> None:
    forbidden = [rid for rid in _extract_run_ids(results) if _run_num(rid) >= _run_num(CUTOFF_RUN_ID)]
    if forbidden:
        raise SystemExit(f"Forbidden discarded run id(s) present in clean seed payload: {sorted(set(forbidden))}")


def _discard_audit(scan_root: Path, retained_results: list[dict]) -> dict:
    observed = sorted(set(_extract_run_ids_from_files(scan_root)), key=_run_num)
    retained = _run_ids(retained_results)
    excluded = [rid for rid in observed if _run_num(rid) >= _run_num(CUTOFF_RUN_ID)]
    return {
        "cutoff_run_id": CUTOFF_RUN_ID,
        "rule": "exclude every RoboFlex run id R0068 or later from BO-MCP clean seed recreation",
        "observed_run_ids_in_scan_root": observed,
        "retained_run_ids_in_seed": retained,
        "excluded_run_ids": excluded,
        "scan_root": str(scan_root.relative_to(ROOT) if scan_root.is_relative_to(ROOT) else scan_root),
    }


def _extract_run_ids_from_files(root: Path) -> list[str]:
    run_ids: list[str] = []
    if not root.exists():
        return run_ids
    for path in root.rglob("*.json"):
        try:
            run_ids.extend(_extract_run_ids(json.loads(path.read_text())))
        except Exception:
            continue
    return run_ids


def _extract_run_ids(payload: object) -> list[str]:
    text = json.dumps(payload)
    return re.findall(r"R\d{4}", text)


def _run_ids(results: list[dict]) -> list[str]:
    return sorted(set(_extract_run_ids(results)), key=_run_num)


def _run_num(run_id: str) -> int:
    return int(run_id[1:])


def _create_campaign(client: BoMcpClient, intake: dict, run_nonce: str | None) -> str:
    key = BoMcpClient.make_idempotency_key("yield-only-clean21-campaign", intake["name"], _run_nonce(run_nonce))
    return client.create_campaign(intake, idempotency_key=key)["campaign_id"]


def _artifact_dir(path: Path | None, prefix: str) -> Path:
    return path or ROOT / "artifacts" / f"{prefix}_{_stamp()}"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _run_nonce(value: str | None) -> str:
    return value or os.environ.get("YIELD_ONLY_RUN_NONCE") or uuid4().hex[:10]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
