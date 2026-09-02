from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Stage1bConfig

REQUIRED_EXPORT_COLUMNS = {
    "param_cap_id",
    "param_bridge_id",
    "param_core_id",
    "obj_bright_osc_strength",
    "obj_color_error_ev",
    "obj_ambiguity_penalty",
}


def load_legacy_export_rows(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_EXPORT_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Legacy export {path} is missing required columns: {missing}")
    return frame


def build_import_rows(config: Stage1bConfig, legacy_frame: pd.DataFrame, candidate_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    outside_space: list[str] = []
    seen: set[str] = set()
    for row in legacy_frame.itertuples(index=False):
        candidate_id = f"{row.param_cap_id}{row.param_bridge_id}{row.param_core_id}"
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        if candidate_id not in candidate_ids:
            outside_space.append(candidate_id)
            continue
        rows.append(
            {
                "candidate_id": candidate_id,
                "parameter_values": {
                    "cap_id": str(row.param_cap_id),
                    "bridge_id": str(row.param_bridge_id),
                    "core_id": str(row.param_core_id),
                },
                "objective_values": {
                    "bright_osc_strength": float(row.obj_bright_osc_strength),
                    "color_error_ev": float(row.obj_color_error_ev),
                    "ambiguity_penalty": float(row.obj_ambiguity_penalty),
                },
                "metadata": {
                    "experiment_id": candidate_id,
                    "conditions": {
                        "imported_from_campaign_id": config.legacy_campaign_id,
                        "imported_from_export": str(config.legacy_export_csv),
                    },
                    "notes": json.dumps(
                        {
                            "candidate_id": candidate_id,
                            "import_type": "legacy_stage1_success",
                            "legacy_campaign_id": config.legacy_campaign_id,
                            "legacy_export_csv": str(config.legacy_export_csv),
                            "legacy_result_id": getattr(row, "result_id", None),
                            "legacy_suggestion_id": getattr(row, "suggestion_id", None),
                            "legacy_created_at": getattr(row, "created_at", None),
                        },
                        sort_keys=True,
                    ),
                },
            }
        )
    summary = {
        "source_count": int(len(legacy_frame)),
        "importable_count": int(len(rows)),
        "outside_space_count": int(len(outside_space)),
        "outside_space_candidate_ids": outside_space,
        "import_candidate_ids": [row["candidate_id"] for row in rows],
    }
    return rows, summary


def existing_campaign_candidate_ids_from_export(content: bytes, content_type: str) -> set[str]:
    if not content:
        return set()
    if "csv" not in content_type:
        raise ValueError(f"Expected CSV campaign export, got content type {content_type}")
    text = content.decode("utf-8")
    if not text.strip():
        return set()
    reader = csv.DictReader(io.StringIO(text))
    candidate_ids: set[str] = set()
    for row in reader:
        cap_id = (row.get("param_cap_id") or "").strip()
        bridge_id = (row.get("param_bridge_id") or "").strip()
        core_id = (row.get("param_core_id") or "").strip()
        if cap_id and bridge_id and core_id:
            candidate_ids.add(f"{cap_id}{bridge_id}{core_id}")
    return candidate_ids


def import_rows_as_frame(import_rows: list[dict[str, Any]]) -> pd.DataFrame:
    records = []
    for row in import_rows:
        records.append(
            {
                "candidate_id": row["candidate_id"],
                "cap_id": row["parameter_values"]["cap_id"],
                "bridge_id": row["parameter_values"]["bridge_id"],
                "core_id": row["parameter_values"]["core_id"],
                "bright_osc_strength": row["objective_values"]["bright_osc_strength"],
                "color_error_ev": row["objective_values"]["color_error_ev"],
                "ambiguity_penalty": row["objective_values"]["ambiguity_penalty"],
            }
        )
    return pd.DataFrame(records)
