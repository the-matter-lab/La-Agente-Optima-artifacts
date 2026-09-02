from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import logfire
from domains.bo_mcp.client import BoMcpClient

from .intake import build_intake
from .objectives import green_score
from .space import normalize_candidate

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_RUN_IDS = tuple(f"R{i:04d}" for i in range(44, 53))
CATALYST_COLUMNS = {
    "4CzIPN": "4CzIPN",
    "Ru-bpy-Cl": "Ru bpy Cl",
    "IrCF3ppy": "Ir CF3 ppy",
    "Ir-ppy": "Ir ppy",
    "Ru-bpy-PF": "Ru bpy PF6",
}
OXIDANT_COLUMNS = {"PyNO": "py NO", "4PhPyNO": "4-Ph py NO"}


def run(args: argparse.Namespace) -> None:
    artifact_dir = Path(args.artifact_dir or ROOT / "artifacts" / f"recreated_robochemflex_yield_bo_{_stamp()}")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    source_csv = Path(args.history_csv)
    if not source_csv.is_absolute():
        source_csv = ROOT / source_csv

    intake = build_intake(args.campaign_name or f"robochemflex_yield_baybe_recreated_{_stamp()}")
    rows = _load_exact_history(source_csv)
    results = [_result_from_row(row) for row in rows]
    _validate_against_intake(results, intake)

    _write_json(artifact_dir / "intake.json", intake)
    _write_json(artifact_dir / "historical_results_to_import.json", results)
    _write_json(
        artifact_dir / "preflight_summary.json",
        {
            "source_csv": str(source_csv.relative_to(ROOT) if source_csv.is_relative_to(ROOT) else source_csv),
            "expected_run_ids": list(EXPECTED_RUN_IDS),
            "loaded_run_ids": [r["metadata"]["external_ref"]["id"] for r in results],
            "result_count": len(results),
            "will_generate_suggestions": False,
            "will_contact_roboflex": False,
        },
    )

    print(f"Prepared {len(results)} historical result(s): {', '.join(EXPECTED_RUN_IDS)}")
    print("RoboFlex/hardware calls: disabled by design")
    print("BO suggestion generation: disabled by design")
    print(f"Artifacts: {artifact_dir}")

    if args.dry_run:
        print("Dry run complete; no BO-MCP mutation was performed.")
        return

    client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    client.validate_intake(intake)
    campaign_id = args.campaign_id or _create_campaign(client, intake, args.run_nonce)
    (artifact_dir / "bo_campaign_id.txt").write_text(campaign_id + "\n")
    print(f"Created/using BO-MCP campaign: {campaign_id}")

    existing = client.get_results(campaign_id)
    imported = 0
    skipped = 0
    for result in results:
        run_id = result["metadata"]["external_ref"]["id"]
        if _coordinate_exists(existing, result["parameter_values"]):
            skipped += 1
            _append_json(artifact_dir / "import_audit.jsonl", {"run_id": run_id, "action": "skipped_existing_coordinate"})
            print(f"Skipped {run_id}: matching BO result already exists")
            continue
        key = BoMcpClient.make_idempotency_key("recreate-history", campaign_id, run_id)
        response = client.submit_results(campaign_id, results=[result], idempotency_key=key, force=False)
        imported += len(response.get("result_ids", []))
        existing.extend(client.get_results(campaign_id)[-1:])
        _append_json(
            artifact_dir / "import_audit.jsonl",
            {"run_id": run_id, "action": "submitted", "response": response},
        )
        print(f"Imported {run_id}")

    final_results = client.get_results(campaign_id)
    _write_json(artifact_dir / "final_bomcp_results.json", final_results)
    _export(client, campaign_id, artifact_dir)
    _pause_if_running(client, campaign_id)
    _write_json(
        artifact_dir / "recreation_summary.json",
        {
            "campaign_id": campaign_id,
            "source_csv": str(source_csv.relative_to(ROOT) if source_csv.is_relative_to(ROOT) else source_csv),
            "expected_run_ids": list(EXPECTED_RUN_IDS),
            "submitted_count": imported,
            "skipped_existing_count": skipped,
            "final_result_count": len(final_results),
            "generated_suggestions": False,
            "contacted_roboflex": False,
        },
    )
    print(f"Done: imported={imported}, skipped_existing={skipped}, final_results={len(final_results)}")
    print(f"New campaign_id: {campaign_id}")


def _create_campaign(client: BoMcpClient, intake: dict, run_nonce: str | None) -> str:
    nonce = run_nonce or uuid4().hex[:10]
    key = BoMcpClient.make_idempotency_key("recreate-campaign", intake["name"], nonce)
    return client.create_campaign(intake, idempotency_key=key)["campaign_id"]


def _load_exact_history(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        by_run = {row["run_id"]: row for row in csv.DictReader(f)}
    missing = [rid for rid in EXPECTED_RUN_IDS if rid not in by_run]
    if missing:
        raise SystemExit(f"Missing required completed run(s): {', '.join(missing)}")
    invalid_present = [rid for rid in ("R0042", "R0043") if rid in by_run]
    if invalid_present:
        logfire.info("Invalid older runs are present in source CSV but excluded", run_ids=invalid_present)
    return [by_run[rid] for rid in EXPECTED_RUN_IDS]


def _result_from_row(row: dict[str, str]) -> dict:
    run_id = row["run_id"]
    if row.get("status") != "completed" or row.get("success") != "True":
        raise SystemExit(f"{run_id} is not a valid completed successful run")

    candidate = normalize_candidate(
        {
            "catalyst_type": _single_nonempty(row, CATALYST_COLUMNS, run_id, "catalyst"),
            "oxidant_type": _single_nonempty(row, OXIDANT_COLUMNS, run_id, "oxidant"),
            "catalyst_equiv": _reagent_value(row, CATALYST_COLUMNS, run_id),
            "TFAA_equiv": _number_with_unit(row["TFAA"]),
            "oxidant_equiv": _reagent_value(row, OXIDANT_COLUMNS, run_id),
            "light_intensity": int(round(_number_with_unit(row["light_intensity"]))),
            "residence_time_min": _number_with_unit(row["residence_time"]) / 60.0,
        }
    )
    y = float(row["yield"])
    if not math.isfinite(y):
        raise SystemExit(f"{run_id} has non-finite yield")
    return {
        "parameter_values": candidate,
        "objective_values": {"yield_percent": y, "green_score": green_score(candidate)},
        "metadata": {
            "external_ref": {"system": "roboflex", "id": run_id},
            "source_file": "roboflex_experiment_log_latest.csv",
            "source_row": int(run_id[1:]) - 42,
            "notes": "historical RoboFlex import; no new hardware run; no BO suggestion generated",
            "conditions": {
                "sample_name": row.get("sample_name") or None,
                "finished_at": row.get("finished_at") or None,
                "original_note": row.get("note") or None,
            },
        },
    }


def _single_nonempty(row: dict[str, str], mapping: dict[str, str], run_id: str, label: str) -> str:
    hits = [mapping[name] for name in mapping if row.get(name, "").strip()]
    if len(hits) != 1:
        raise SystemExit(f"{run_id} has {len(hits)} {label} entries; expected exactly 1")
    return hits[0]


def _reagent_value(row: dict[str, str], mapping: dict[str, str], run_id: str) -> float:
    hits = [_number_with_unit(row[name]) for name in mapping if row.get(name, "").strip()]
    if len(hits) != 1:
        raise SystemExit(f"{run_id} has {len(hits)} reagent values; expected exactly 1")
    return hits[0]


def _number_with_unit(value: str) -> float:
    return float(str(value).strip().split()[0])


def _validate_against_intake(results: list[dict], intake: dict) -> None:
    if [r["metadata"]["external_ref"]["id"] for r in results] != list(EXPECTED_RUN_IDS):
        raise SystemExit("Historical result order/run ids do not match R0044-R0052")
    seen = set()
    param_specs = {p["name"]: p for p in intake["parameters"]}
    for result in results:
        key = json.dumps(result["parameter_values"], sort_keys=True)
        if key in seen:
            raise SystemExit("Duplicate parameter coordinate found in historical imports")
        seen.add(key)
        for name, value in result["parameter_values"].items():
            spec = param_specs[name]
            if spec["type"] == "categorical" and value not in spec["categories"]:
                raise SystemExit(f"{name}={value!r} is outside campaign categories")
            if spec["type"] == "discrete" and value not in spec["values"]:
                raise SystemExit(f"{name}={value!r} is outside campaign discrete values")
            if spec["type"] == "continuous":
                lo, hi = spec["bounds"]["lower"], spec["bounds"]["upper"]
                if not (lo <= float(value) <= hi):
                    raise SystemExit(f"{name}={value!r} is outside bounds [{lo}, {hi}]")
        for obj, value in result["objective_values"].items():
            if obj not in {"yield_percent", "green_score"} or not math.isfinite(float(value)):
                raise SystemExit(f"Invalid objective value for {obj}: {value!r}")


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


def _export(client: BoMcpClient, campaign_id: str, artifact_dir: Path) -> None:
    try:
        content, content_type = client.export_campaign(campaign_id, fmt="csv")
        (artifact_dir / "bo_campaign_export.csv").write_bytes(content)
        (artifact_dir / "bo_campaign_export.content_type.txt").write_text(content_type + "\n")
    except Exception as exc:
        print(f"Export skipped: {exc}")


def _pause_if_running(client: BoMcpClient, campaign_id: str) -> None:
    try:
        status = client.get_campaign(campaign_id).get("status")
        if status == "running":
            client.lifecycle(campaign_id, action="pause")
            print("BO campaign paused after historical import.")
    except Exception as exc:
        print(f"Pause skipped: {exc}")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_json(path: Path, payload) -> None:
    with path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
