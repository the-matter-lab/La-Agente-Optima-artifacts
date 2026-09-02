from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from digital_osl_stage1.fragments import (
    CUSTOM_DESCRIPTOR_COLUMNS,
    _prepare_catalog,
    build_campaign_intake,
    build_candidate_library,
    validate_assembly_against_s6,
)

from .config import ORIGINAL_STAGE1_ACTIVE_IDS, PreparedStage1b, Stage1bConfig
from .legacy_import import build_import_rows, load_legacy_export_rows


OBJECTIVE_DIRECTIONS = {
    "obj_bright_osc_strength": "maximize",
    "obj_color_error_ev": "minimize",
    "obj_ambiguity_penalty": "minimize",
}


def _feasible_catalog(frame: pd.DataFrame) -> pd.DataFrame:
    feasible = frame[frame["compatible_with_gen_2"] & frame["reactive_sites_ok"]].copy()
    feasible = feasible.sort_values(["heavy_atoms", "exact_mw", "rotatable_bonds", "hid"]).reset_index(drop=True)
    return feasible


def _pareto_frontier(frame: pd.DataFrame) -> pd.DataFrame:
    records = frame.to_dict(orient="records")

    def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
        better_or_equal = True
        strictly_better = False
        for column, direction in OBJECTIVE_DIRECTIONS.items():
            if direction == "maximize":
                if a[column] < b[column]:
                    better_or_equal = False
                    break
                if a[column] > b[column]:
                    strictly_better = True
            else:
                if a[column] > b[column]:
                    better_or_equal = False
                    break
                if a[column] < b[column]:
                    strictly_better = True
        return better_or_equal and strictly_better

    keep_indices = []
    for idx, row in enumerate(records):
        if not any(dominates(other, row) for jdx, other in enumerate(records) if jdx != idx):
            keep_indices.append(idx)
    return frame.iloc[keep_indices].reset_index(drop=True)


def _frontier_fragment_ids(frontier: pd.DataFrame, slot: str) -> list[str]:
    column = f"param_{slot}_id"
    return sorted({str(value) for value in frontier[column].tolist()})


def _normalised_descriptor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    descriptors = frame[list(CUSTOM_DESCRIPTOR_COLUMNS)].astype(float)
    std = descriptors.std(ddof=0).replace(0.0, 1.0)
    return (descriptors - descriptors.mean()) / std


def _expand_slot(
    feasible: pd.DataFrame,
    slot: str,
    target_count: int,
    frontier_ids: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    original_ids = ORIGINAL_STAGE1_ACTIVE_IDS[slot]
    if not set(original_ids).issubset(set(feasible["hid"])):
        missing = sorted(set(original_ids).difference(set(feasible["hid"])))
        raise ValueError(f"Original Stage 1 {slot} ids are missing from the feasible catalog: {missing}")
    if target_count > len(feasible):
        raise ValueError(f"Requested {target_count} {slot} fragments but only {len(feasible)} feasible fragments exist")

    norm = _normalised_descriptor_frame(feasible)
    frontier_pool = frontier_ids or list(original_ids)
    frontier_index_lookup = {hid: int(feasible.index[feasible["hid"] == hid][0]) for hid in frontier_pool}
    original_set = set(original_ids)
    scored: list[tuple[float, float, float, str, str]] = []
    expansion_report: list[dict[str, Any]] = []

    for idx, row in feasible.iterrows():
        hid = str(row["hid"])
        if hid in original_set:
            continue
        nearest_anchor = None
        nearest_distance = None
        for anchor_id, anchor_idx in frontier_index_lookup.items():
            distance = float(math.dist(norm.loc[idx].tolist(), norm.loc[anchor_idx].tolist()))
            if nearest_distance is None or distance < nearest_distance or (
                math.isclose(distance, nearest_distance) and anchor_id < (nearest_anchor or anchor_id)
            ):
                nearest_distance = distance
                nearest_anchor = anchor_id
        assert nearest_anchor is not None and nearest_distance is not None
        scored.append((nearest_distance, float(row["heavy_atoms"]), float(row["exact_mw"]), float(row["rotatable_bonds"]), hid))
        expansion_report.append(
            {
                "hid": hid,
                "nearest_frontier_anchor": nearest_anchor,
                "min_descriptor_distance": nearest_distance,
                "heavy_atoms": float(row["heavy_atoms"]),
                "exact_mw": float(row["exact_mw"]),
            }
        )

    scored.sort()
    selected_extra_ids = [hid for *_rest, hid in scored[: target_count - len(original_ids)]]
    order = original_ids + selected_extra_ids
    selected = feasible.set_index("hid").loc[order].reset_index()
    selected_report = [item for item in expansion_report if item["hid"] in set(selected_extra_ids)]
    selected_report.sort(key=lambda item: order.index(item["hid"]))
    return selected, selected_report


def prepare_stage(config: Stage1bConfig) -> PreparedStage1b:
    materialized = config.materialize()
    caps = _prepare_catalog(materialized.cap_catalog, "cap")
    bridges = _prepare_catalog(materialized.bridge_catalog, "bridge")
    cores = _prepare_catalog(materialized.core_catalog, "core")
    validation_report = validate_assembly_against_s6(caps, bridges, cores, materialized.validation_catalog)
    if validation_report["status"] != "passed":
        raise ValueError(f"Assembly validation failed: {validation_report}")

    legacy_frame = load_legacy_export_rows(materialized.legacy_export_csv)
    if materialized.expected_legacy_successes and len(legacy_frame) != materialized.expected_legacy_successes:
        raise ValueError(
            f"Legacy export row count {len(legacy_frame)} did not match expected_legacy_successes={materialized.expected_legacy_successes}"
        )
    frontier = _pareto_frontier(legacy_frame)

    feasible_caps = _feasible_catalog(caps)
    feasible_bridges = _feasible_catalog(bridges)
    feasible_cores = _feasible_catalog(cores)
    active_caps, cap_expansion = _expand_slot(
        feasible_caps,
        slot="cap",
        target_count=materialized.cap_target,
        frontier_ids=_frontier_fragment_ids(frontier, "cap"),
    )
    active_bridges, bridge_expansion = _expand_slot(
        feasible_bridges,
        slot="bridge",
        target_count=materialized.bridge_target,
        frontier_ids=_frontier_fragment_ids(frontier, "bridge"),
    )
    active_cores, core_expansion = _expand_slot(
        feasible_cores,
        slot="core",
        target_count=materialized.core_target,
        frontier_ids=_frontier_fragment_ids(frontier, "core"),
    )

    candidate_library = build_candidate_library(active_caps, active_bridges, active_cores)
    candidate_ids = set(candidate_library["candidate_id"].tolist())
    legacy_import_rows, legacy_import_summary = build_import_rows(materialized, legacy_frame, candidate_ids)
    if not materialized.skip_legacy_import and legacy_import_summary["outside_space_count"]:
        raise ValueError(
            "Legacy results fell outside the Stage 1b search space despite the required superset guarantee: "
            f"{legacy_import_summary['outside_space_candidate_ids']}"
        )
    if not materialized.skip_legacy_import and materialized.expected_legacy_successes:
        if legacy_import_summary["importable_count"] != materialized.expected_legacy_successes:
            raise ValueError(
                f"Expected to import {materialized.expected_legacy_successes} legacy observations, "
                f"but the plan found {legacy_import_summary['importable_count']}"
            )

    intake, intake_backend, descriptor_columns = build_campaign_intake(materialized, active_caps, active_bridges, active_cores)
    preview_summary = {
        "assembly_validation": validation_report,
        "active_fragment_counts": {
            "caps": int(len(active_caps)),
            "bridges": int(len(active_bridges)),
            "cores": int(len(active_cores)),
            "candidate_count": int(len(candidate_library)),
        },
        "active_fragments": {
            "caps": active_caps[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
            "bridges": active_bridges[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
            "cores": active_cores[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
        },
        "original_stage1_active_ids": ORIGINAL_STAGE1_ACTIVE_IDS,
        "superset_guarantee": {
            "caps_include_original": set(ORIGINAL_STAGE1_ACTIVE_IDS["cap"]).issubset(set(active_caps["hid"])),
            "bridges_include_original": set(ORIGINAL_STAGE1_ACTIVE_IDS["bridge"]).issubset(set(active_bridges["hid"])),
            "cores_include_original": set(ORIGINAL_STAGE1_ACTIVE_IDS["core"]).issubset(set(active_cores["hid"])),
            "original_candidate_count": 360,
            "new_candidate_count": int(len(candidate_library)),
        },
        "frontier_expansion": {
            "legacy_frontier_candidate_ids": [
                f"{row.param_cap_id}{row.param_bridge_id}{row.param_core_id}" for row in frontier.itertuples(index=False)
            ],
            "legacy_frontier_fragment_ids": {
                "cap": _frontier_fragment_ids(frontier, "cap"),
                "bridge": _frontier_fragment_ids(frontier, "bridge"),
                "core": _frontier_fragment_ids(frontier, "core"),
            },
            "added_caps": cap_expansion,
            "added_bridges": bridge_expansion,
            "added_cores": core_expansion,
        },
        "legacy_import_summary": legacy_import_summary,
        "descriptor_columns": descriptor_columns,
        "intake": intake,
        "intake_backend": intake_backend,
    }
    return PreparedStage1b(
        config=materialized,
        cap_catalog=caps,
        bridge_catalog=bridges,
        core_catalog=cores,
        validation_report=validation_report,
        active_caps=active_caps,
        active_bridges=active_bridges,
        active_cores=active_cores,
        candidate_library=candidate_library,
        legacy_import_rows=legacy_import_rows,
        legacy_import_summary=legacy_import_summary,
        intake=intake,
        intake_backend=intake_backend,
        preview_summary=preview_summary,
    )
