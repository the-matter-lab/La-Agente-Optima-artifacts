from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from robochemflex_yield_bo.objectives import green_score
from robochemflex_yield_bo.space import normalize_candidate

PARAM_COLUMNS = {
    "catalyst_type": "param_catalyst_type",
    "oxidant_type": "param_oxidant_type",
    "catalyst_equiv": "param_catalyst_equiv",
    "TFAA_equiv": "param_TFAA_equiv",
    "oxidant_equiv": "param_oxidant_equiv",
    "light_intensity": "param_light_intensity",
    "residence_time_min": "param_residence_time_min",
}
INVALID_RUN_IDS = {"R0060", "R0063", "R0064"}
SUCCESSFUL_RETRIES = {"R0061", "R0065"}


def load_seed_results(export_csv: Path, expected_count: int = 20) -> list[dict]:
    with export_csv.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != expected_count:
        raise SystemExit(f"Expected {expected_count} historical BO result rows, found {len(rows)} in {export_csv}")
    results = [_seed_result(row, i) for i, row in enumerate(rows, start=1)]
    _reject_invalid_run_ids(results)
    return results


def audit_rows(export_csv: Path) -> list[dict]:
    with export_csv.open(newline="") as f:
        return list(csv.DictReader(f))


def _seed_result(row: dict[str, str], index: int) -> dict:
    candidate = normalize_candidate({name: row[col] for name, col in PARAM_COLUMNS.items()})
    y = float(row.get("obj_yield_percent") or row.get("yield_percent") or "nan")
    if not math.isfinite(y):
        raise SystemExit(f"Historical row {index} has non-finite yield_percent")
    prior_green = _optional_float(row.get("obj_green_score") or row.get("green_score"))
    computed_green = green_score(candidate)
    result_id = row.get("result_id") or f"row-{index}"
    suggestion_id = row.get("suggestion_id") or None
    return {
        "parameter_values": candidate,
        "objective_values": {"yield_percent": y},
        "suggestion_id": suggestion_id,
        "metadata": {
            "external_ref": {"system": "bo_mcp_prior_campaign", "id": result_id},
            "source_file": "bo_campaign_export.csv",
            "source_row": index,
            "notes": "yield-only historical seed from valid prior mixed-objective BO result; green score is audit metadata only",
            "conditions": {
                "prior_mixed_objective_result_id": result_id,
                "prior_suggestion_id": suggestion_id,
                "prior_green_score": prior_green,
                "computed_green_score_audit": computed_green,
            },
        },
    }


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _reject_invalid_run_ids(results: list[dict]) -> None:
    text = json.dumps(results)
    bad = sorted(rid for rid in INVALID_RUN_IDS if rid in text)
    if bad:
        raise SystemExit(f"Invalid failed NMR run id(s) present in seed metadata: {', '.join(bad)}")
