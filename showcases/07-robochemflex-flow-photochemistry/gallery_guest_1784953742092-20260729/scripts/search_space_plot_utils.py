from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_EXPORT_ROOTS = [Path("artifacts/yield_only_robochemflex_bo"), Path("artifacts/recreated_robochemflex_yield_bo_20260725")]
DEFAULT_INTAKE_ROOTS = [Path("artifacts/yield_only_recreation_20260727T013936Z"), Path("artifacts/recreated_robochemflex_yield_bo_20260725")]

PARAMS = [
    "catalyst_type",
    "oxidant_type",
    "catalyst_equiv",
    "TFAA_equiv",
    "oxidant_equiv",
    "light_intensity",
    "residence_time_min",
]
NUMERIC_PARAMS = ["catalyst_equiv", "TFAA_equiv", "oxidant_equiv", "light_intensity", "residence_time_min"]
CAT_PARAMS = ["catalyst_type", "oxidant_type"]


def discover_export(search_roots: list[Path] | None = None) -> Path:
    roots = search_roots or DEFAULT_EXPORT_ROOTS
    candidates: list[Path] = []
    for root in roots:
        if root.exists():
            candidates.extend(root.rglob("bo_campaign_export.csv"))
    if not candidates:
        raise FileNotFoundError(f"No bo_campaign_export.csv found under {[str(r) for r in roots]}")

    def score(path: Path) -> tuple[int, float]:
        try:
            n = len(pd.read_csv(path))
        except Exception:
            n = -1
        return (n, path.stat().st_mtime)

    return max(candidates, key=score)


def discover_intake(search_roots: list[Path] | None = None) -> Path | None:
    roots = search_roots or DEFAULT_INTAKE_ROOTS
    names = ["yield_only_intake.json", "intake.json"]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for name in names:
            candidates.extend(root.rglob(name))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_intake(path: Path | None = None) -> dict[str, Any]:
    path = path or discover_intake()
    if path and path.exists():
        return json.loads(path.read_text())
    # Fallback from historical campaign settings; scripts do not hard-code results.
    return {
        "parameters": [
            {"name": "catalyst_type", "type": "categorical", "categories": ["Ru bpy Cl", "Ru bpy PF6", "Ir ppy", "Ir CF3 ppy", "4CzIPN"]},
            {"name": "oxidant_type", "type": "categorical", "categories": ["py NO", "4-Ph py NO"]},
            {"name": "catalyst_equiv", "type": "continuous", "bounds": {"lower": 0.001, "upper": 0.004}},
            {"name": "TFAA_equiv", "type": "continuous", "bounds": {"lower": 0.9, "upper": 3.5}},
            {"name": "oxidant_equiv", "type": "continuous", "bounds": {"lower": 0.9, "upper": 3.0}},
            {"name": "light_intensity", "type": "discrete", "values": [0, 25, 50, 75, 100]},
            {"name": "residence_time_min", "type": "continuous", "bounds": {"lower": 2.0, "upper": 90.0}},
        ]
    }


def parameter_specs(intake: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for p in intake.get("parameters", [])}


def load_valid_export(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    df = pd.DataFrame()
    for p in PARAMS:
        col = f"param_{p}"
        if col not in raw.columns:
            raise ValueError(f"{path} missing required column {col}")
        df[p] = raw[col]
    if "obj_yield_percent" not in raw.columns:
        raise ValueError(f"{path} missing obj_yield_percent")
    df["yield_percent"] = pd.to_numeric(raw["obj_yield_percent"], errors="coerce")
    df["green_score"] = pd.to_numeric(raw.get("obj_green_score", np.nan), errors="coerce")
    df["suggestion_id"] = raw.get("suggestion_id", pd.Series([None] * len(raw))).astype("object")
    df["result_id"] = raw.get("result_id", pd.Series([None] * len(raw))).astype("object")
    df["created_at"] = raw.get("created_at", pd.Series([None] * len(raw))).astype("object")
    df["valid_bo_result"] = True
    df["status"] = "valid"
    df["source"] = str(path)
    df["experiment"] = np.arange(1, len(df) + 1)
    df["stage"] = np.where(df["experiment"] <= 6, "seed", np.where(df["experiment"] <= 20, "mixed-objective BO", "yield-only BO"))
    return df


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _sample_name_from_request(req: dict[str, Any] | None) -> str | None:
    if not isinstance(req, dict):
        return None
    for p in req.get("parameters", []):
        if isinstance(p, dict) and p.get("name") == "sample_name":
            return str(p.get("value"))
    note = req.get("note")
    if note:
        m = re.search(r"bo_[A-Za-z0-9_-]+", str(note))
        if m:
            return m.group(0)
    return None


def _result_summary(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    payload = result.get("result")
    out = {"roboflex_run_id": result.get("run_id"), "roboflex_status": result.get("status"), "roboflex_error": result.get("error")}
    if isinstance(payload, dict):
        out["yield_percent"] = payload.get("yield")
        out["result_pass"] = payload.get("pass")
    return out


def load_failed_tested_points(artifact_roots: list[Path] | None = None) -> pd.DataFrame:
    roots = artifact_roots or [Path("artifacts/recreated_robochemflex_yield_bo_20260725"), Path("artifacts/yield_only_robochemflex_bo")]
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        for cand_path in root.rglob("candidate.json"):
            d = cand_path.parent
            cand = _read_json(cand_path)
            if not isinstance(cand, dict) or not all(p in cand for p in PARAMS):
                continue
            result = _read_json(d / "roboflex_result.json")
            final_record = _read_json(d / "roboflex_final_run_record.json")
            request = _read_json(d / "roboflex_request.json")
            suggestion = _read_json(d / "suggestion.json")
            status = None
            if isinstance(result, dict):
                status = result.get("status")
            if status != "failed":
                # We only append unsubmitted failed attempts; valid attempts should be in BO export.
                continue
            row = {p: cand[p] for p in PARAMS}
            row.update(_result_summary(result))
            row["yield_percent"] = pd.to_numeric(row.get("yield_percent"), errors="coerce")
            row["green_score"] = np.nan
            row["suggestion_id"] = suggestion.get("suggestion_id") if isinstance(suggestion, dict) else None
            row["result_id"] = None
            row["created_at"] = result.get("finished_at") if isinstance(result, dict) else None
            row["valid_bo_result"] = False
            row["status"] = "failed/not submitted"
            row["stage"] = "failed/not submitted"
            row["sample_name"] = _sample_name_from_request(request)
            row["source"] = str(d)
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=PARAMS + ["yield_percent", "green_score", "valid_bo_result", "status", "stage", "source"])
    df = pd.DataFrame(rows)
    # Stable order by path; experiment is left NaN for failed attempts because they are not BO results.
    df["experiment"] = np.nan
    return df


def load_points(export: Path | None = None, include_failed: bool = True) -> tuple[pd.DataFrame, Path]:
    source = export or discover_export()
    valid = load_valid_export(source)
    if include_failed:
        failed = load_failed_tested_points()
        if not failed.empty:
            # Avoid adding failed attempts that somehow match a valid result_id unavailable; keep attempts for coverage.
            df = pd.concat([valid, failed], ignore_index=True, sort=False)
        else:
            df = valid
    else:
        df = valid
    for p in NUMERIC_PARAMS + ["yield_percent", "green_score"]:
        if p in df.columns:
            df[p] = pd.to_numeric(df[p], errors="coerce")
    return df, source


def normalize_param(series: pd.Series, spec: dict[str, Any]) -> tuple[pd.Series, list[tuple[float, str]]]:
    typ = spec.get("type")
    if typ == "categorical":
        cats = list(spec.get("categories", []))
        mapping = {c: i for i, c in enumerate(cats)}
        denom = max(1, len(cats) - 1)
        vals = series.map(mapping) / denom
        ticks = [(i / denom, str(c)) for i, c in enumerate(cats)]
        return vals, ticks
    if typ == "discrete":
        values = list(spec.get("values", []))
        lo, hi = float(min(values)), float(max(values))
        vals = (pd.to_numeric(series, errors="coerce") - lo) / (hi - lo if hi != lo else 1.0)
        ticks = [((float(v) - lo) / (hi - lo if hi != lo else 1.0), str(v)) for v in values]
        return vals, ticks
    bounds = spec.get("bounds") or {}
    lo, hi = float(bounds.get("lower", pd.to_numeric(series, errors="coerce").min())), float(bounds.get("upper", pd.to_numeric(series, errors="coerce").max()))
    vals = (pd.to_numeric(series, errors="coerce") - lo) / (hi - lo if hi != lo else 1.0)
    ticks = [(0.0, f"{lo:g}"), (0.5, f"{(lo+hi)/2:g}"), (1.0, f"{hi:g}")]
    return vals, ticks


def stage_markers() -> dict[str, str]:
    return {"seed": "o", "mixed-objective BO": "o", "yield-only BO": "D", "failed/not submitted": "x"}


def stage_colors() -> dict[str, str]:
    return {"seed": "#4C78A8", "mixed-objective BO": "#F58518", "yield-only BO": "#54A24B", "failed/not submitted": "#777777"}
