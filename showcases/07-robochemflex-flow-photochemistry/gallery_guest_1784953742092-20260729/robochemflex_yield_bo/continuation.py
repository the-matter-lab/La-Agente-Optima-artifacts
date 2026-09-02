from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from domains.bo_mcp.client import BoMcpClient

from .robridge_client import RobridgeClient
from .space import normalize_candidate, robridge_parameters

DEFAULT_CAMPAIGN_ID = "ccbfc92e-c646-4943-a44d-9277f2f2d8d4"
DEFAULT_ARTIFACT_DIR = Path("artifacts/recreated_robochemflex_yield_bo_20260725/measurement10_preview")
DEFAULT_HISTORY = Path("artifacts/real_robochemflex_yield_bo_fresh_20260724T155503Z/robridge_results.jsonl")
DEFAULT_ROBRIDGE_CAMPAIGN = "robochemflex_yield_bo_fresh_20260724T155503Z-20260724-175502"
BO_KEYS = {
    "catalyst_type",
    "oxidant_type",
    "catalyst_equiv",
    "TFAA_equiv",
    "oxidant_equiv",
    "light_intensity",
    "residence_time_min",
}
FIXED_NAMES = {
    "slug_volume",
    "collect_crude",
    "SM",
    "target_peak",
    "metric",
    "yield_calculation_chemical",
    "target_peak_deviation",
    "centerFrequency",
    "target_peak_calibration_coeff_1",
    "target_peak_calibration_coeff_0",
    "protocol",
    "AcquisitionTime",
    "Number",
}
VARYING_REQUEST_NAMES = {"light_intensity", "residence_time", "sample_name", "TFAA"}
VARYING_ROLES = {"Catalyst", "Oxidant"}


def run(args: argparse.Namespace) -> None:
    artifact_dir = Path(args.artifact_dir or DEFAULT_ARTIFACT_DIR)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if args.submit:
        _submit_reviewed(args, artifact_dir)
    else:
        _preview(args, artifact_dir)


def _preview(args: argparse.Namespace, artifact_dir: Path) -> None:
    client = BoMcpClient.from_env(timeout_s=args.bo_timeout_s)
    campaign_id = args.campaign_id
    results = client.get_results(campaign_id)
    if len(results) != args.expected_completed_results:
        raise SystemExit(f"Expected {args.expected_completed_results} BO results before measurement 10, found {len(results)}; refusing to generate.")
    pending = client.query_suggestions(campaign_id, status_filter="pending", limit=2)
    if len(pending) > 1:
        ids = ", ".join(s["suggestion_id"] for s in pending)
        raise SystemExit(f"Found multiple pending BO suggestions ({ids}); refusing to choose one.")
    if pending:
        suggestion = pending[0]
        generated_now = False
    else:
        decision = client.next_action(campaign_id)
        if decision.get("action") != "bo_generate_suggestions":
            raise SystemExit(f"BO next_action={decision.get('action')!r}; refusing to generate a measurement-10 suggestion.")
        response = client.generate_suggestions(campaign_id, batch_size=1)
        suggestions = response.get("suggestions", [])
        if len(suggestions) != 1:
            raise SystemExit(f"Expected exactly one generated suggestion, received {len(suggestions)}.")
        suggestion = suggestions[0]
        generated_now = True
    candidate = normalize_candidate(suggestion["parameter_values"])
    if set(candidate) != BO_KEYS:
        raise SystemExit(f"Unexpected candidate keys: {sorted(candidate)}")
    label = f"bo_{suggestion['suggestion_id'][:10]}"
    request = {"parameters": robridge_parameters(candidate, sample_name=label), "note": f"BO-MCP RoboChemFlex yield optimization {label}"}
    report = _equivalence_report(request, args.history_path)
    _ensure_report_passes(report)
    duplicate = _visible_duplicate(label)
    if duplicate:
        raise SystemExit(f"Visible RoboFlex run {duplicate.get('run_id')} already uses {label}; refusing duplicate preview/submission.")
    payload = {
        "campaign_id": campaign_id,
        "measurement_number": 10,
        "generated_now": generated_now,
        "suggestion": suggestion,
        "candidate": candidate,
        "sample_name": label,
        "created_at": _iso_now(),
    }
    _write_json(artifact_dir / "measurement10_suggestion.json", payload)
    _write_json(artifact_dir / "measurement10_roboflex_request.json", request)
    _write_json(artifact_dir / "measurement10_equivalence_report.json", report)
    _write_submit_command(artifact_dir, args)
    print("Preview written; RoboFlex was not submitted.")
    print(f"BO suggestion: {suggestion['suggestion_id']} ({'generated now' if generated_now else 'existing pending'})")
    print(f"Sample name: {label}")
    print(f"Artifacts: {artifact_dir}")


def _submit_reviewed(args: argparse.Namespace, artifact_dir: Path) -> None:
    if not args.confirm_reviewed:
        raise SystemExit("Submission requires --confirm-reviewed after inspecting the preview artifacts.")
    request_path = artifact_dir / "measurement10_roboflex_request.json"
    suggestion_path = artifact_dir / "measurement10_suggestion.json"
    if not request_path.exists() or not suggestion_path.exists():
        raise SystemExit("Preview artifacts are missing; run preview mode first.")
    request = json.loads(request_path.read_text())
    suggestion = json.loads(suggestion_path.read_text())
    label = suggestion["sample_name"]
    if (artifact_dir / "measurement10_submission_response.json").exists() and not args.force_resubmit:
        raise SystemExit("Submission artifact already exists; refusing to submit again without --force-resubmit.")
    report = _equivalence_report(request, args.history_path)
    _ensure_report_passes(report)
    _write_json(artifact_dir / "measurement10_equivalence_report.resubmit_check.json", report)
    rb = RobridgeClient()
    status = rb.status()
    _ensure_robot_ready(status, args)
    unfinished = [r for r in rb.list_runs().get("runs", []) if r.get("status") in {"queued", "running"}]
    if unfinished:
        ids = ", ".join(f"{r.get('run_id')}:{r.get('status')}" for r in unfinished)
        raise SystemExit(f"RoboFlex has unfinished run(s) visible ({ids}); refusing duplicate submission.")
    duplicate = _duplicate_run(rb, label)
    if duplicate and not args.force_resubmit:
        raise SystemExit(f"RoboFlex run {duplicate.get('run_id')} already uses {label}; refusing duplicate submission.")
    response = rb.submit_run(request["parameters"], request.get("note", ""))
    _write_json(artifact_dir / "measurement10_submission_response.json", {"submitted_at": _iso_now(), "response": response})
    print("Submitted reviewed RoboFlex request.")
    print(f"Run id: {response.get('run', {}).get('run_id')}")
    print(f"Artifacts: {artifact_dir}")


def _ensure_robot_ready(status: dict, args: argparse.Namespace) -> None:
    progress = status.get("progress") or {}
    active = progress.get("active_run_ids") or []
    campaign = status.get("campaign") or {}
    campaign_name = campaign.get("campaign_name") if isinstance(campaign, dict) else None
    checks = [
        (status.get("mode") == "hardware", f"mode is {status.get('mode')!r}, not hardware"),
        (status.get("phase") == "running", f"phase is {status.get('phase')!r}, not running"),
        (progress.get("state") == "awaiting_run", f"progress.state is {progress.get('state')!r}, not awaiting_run"),
        ((progress.get("queue_depth") or 0) == 0, f"queue_depth is {progress.get('queue_depth')!r}, not 0"),
        (not active, f"active_run_ids is {active!r}, not empty"),
        (status.get("runs_failed") == 0, f"runs_failed is {status.get('runs_failed')!r}, not 0"),
        (campaign_name == args.expected_robridge_campaign, f"campaign_name is {campaign_name!r}, not {args.expected_robridge_campaign!r}"),
    ]
    failures = [msg for ok, msg in checks if not ok]
    if failures:
        raise SystemExit("RoboFlex status is not the expected idle active hardware campaign: " + "; ".join(failures))


def _equivalence_report(request: dict, history_path: Path | str) -> dict:
    history = _load_history(Path(history_path))
    reference = history[-1]["result"]["parameters"]
    current = request["parameters"]
    fixed_mismatches = []
    schema_mismatches = []
    expected_differences = []
    by_name_ref = _index_reference(reference)
    by_name_cur = {p["name"]: p for p in current}
    if len(current) != len(reference):
        schema_mismatches.append({"field": "parameter_count", "reference": len(reference), "current": len(current)})
    for name in FIXED_NAMES:
        ref = by_name_ref.get(name)
        cur = by_name_cur.get(name)
        if not ref or not cur:
            fixed_mismatches.append({"name": name, "problem": "missing fixed parameter"})
            continue
        for field in ("value", "role"):
            rv = _comparable(ref.get(field))
            cv = _comparable(cur.get(field))
            if rv != cv:
                fixed_mismatches.append({"name": name, "field": field, "reference": rv, "current": cv})
        if "units" in cur and _comparable(ref.get("units")) != _comparable(cur.get("units")):
            fixed_mismatches.append({"name": name, "field": "units", "reference": ref.get("units"), "current": cur.get("units")})
        if cur.get("kind") == "chemical" and ref.get("kind") != "chemical":
            fixed_mismatches.append({"name": name, "field": "kind", "reference": ref.get("kind"), "current": cur.get("kind")})
    for param in current:
        name = param.get("name")
        role = param.get("role")
        if name in VARYING_REQUEST_NAMES or role in VARYING_ROLES:
            expected_differences.append({"name": name, "role": role, "value": param.get("value"), "units": param.get("units")})
    unknown = [p.get("name") for p in current if p.get("name") not in FIXED_NAMES | VARYING_REQUEST_NAMES and p.get("role") not in VARYING_ROLES]
    if unknown:
        schema_mismatches.append({"field": "unknown_parameters", "current": unknown})
    return {
        "history_path": str(history_path),
        "reference_run_id": history[-1].get("run_id"),
        "fixed_fields_match": not fixed_mismatches,
        "schema_matches_reference": not schema_mismatches,
        "fixed_mismatches": fixed_mismatches,
        "schema_mismatches": schema_mismatches,
        "expected_differences": expected_differences,
        "checked_at": _iso_now(),
    }


def _index_reference(parameters: list[dict]) -> dict[str, dict]:
    indexed = {}
    for p in parameters:
        q = dict(p)
        if "kind" not in q and q.get("type") == "ChemicalParameter":
            q["kind"] = "chemical"
        elif "kind" not in q and q.get("type") == "NumericalParameter":
            q["kind"] = "physical"
        indexed[q.get("name")] = q
    return indexed


def _ensure_report_passes(report: dict) -> None:
    if not report["fixed_fields_match"] or not report["schema_matches_reference"]:
        raise SystemExit("Request/history equivalence check failed; inspect measurement10_equivalence_report.json.")


def _load_history(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"No historical RoboFlex rows found at {path}")
    return rows


def _visible_duplicate(label: str) -> dict | None:
    try:
        return _duplicate_run(RobridgeClient(), label)
    except Exception:
        return None


def _duplicate_run(client: RobridgeClient, label: str) -> dict | None:
    for run in client.list_runs().get("runs", []):
        note = str(run.get("note") or "")
        sample_names = [p.get("value") for p in run.get("parameters", []) if isinstance(p, dict) and p.get("name") == "sample_name"]
        if label in note or label in sample_names:
            return run
    return None


def _comparable(value):
    if isinstance(value, float):
        return round(value, 10)
    return value


def _write_submit_command(artifact_dir: Path, args: argparse.Namespace) -> None:
    command = (
        "uv run python continue_robochemflex_yield_bo.py \\\n"
        f"  --campaign-id {args.campaign_id} \\\n"
        f"  --artifact-dir {artifact_dir} \\\n"
        f"  --history-path {args.history_path} \\\n"
        "  --submit --confirm-reviewed\n"
    )
    (artifact_dir / "SUBMIT_MEASUREMENT10_COMMAND.txt").write_text(command)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
