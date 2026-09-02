from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from .evaluator import PENALTY_ANGLE_DEG
from .search_space import ETHANOL_BOUNDS, SDS_BOUNDS


@dataclass(frozen=True)
class SeedSource:
    campaign_id: str
    export_path: Path


DEFAULT_SEED_SOURCES: Final[tuple[SeedSource, ...]] = (
    SeedSource(
        campaign_id="5be855ea-96e2-4a4b-b564-d06bf18de9a5",
        export_path=Path(
            "artifacts/ethanol_sds_contact_angle_65/20260715T170509Z__5be855ea/campaign_export.csv"
        ),
    ),
    SeedSource(
        campaign_id="e799b16b-d208-4d60-a115-72a67cac3130",
        export_path=Path(
            "artifacts/ethanol_sds_contact_angle_65/20260715T180237Z__e799b16b/campaign_export.csv"
        ),
    ),
)


@dataclass
class SeedRowDetail:
    result_id: str
    reason: str


@dataclass
class SeedSourceSummary:
    source_campaign_id: str
    source_export_path: str
    total_rows: int = 0
    valid_rows: int = 0
    seeded_rows: int = 0
    excluded_rows: int = 0
    duplicate_rows: int = 0
    excluded_result_ids: list[SeedRowDetail] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeedInspectionSummary:
    combined_seeded_rows: int
    combined_valid_rows: int
    combined_excluded_rows: int
    combined_duplicate_rows: int
    sources: list[SeedSourceSummary]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _in_bounds(candidate: dict[str, float]) -> bool:
    return (
        ETHANOL_BOUNDS[0] <= candidate["Ethanol"] <= ETHANOL_BOUNDS[1]
        and SDS_BOUNDS[0] <= candidate["SDS"] <= SDS_BOUNDS[1]
    )


def _candidate_key(candidate: dict[str, float]) -> tuple[float, float]:
    return (round(candidate["Ethanol"], 6), round(candidate["SDS"], 6))


def load_seed_results(
    *,
    sources: tuple[SeedSource, ...] = DEFAULT_SEED_SOURCES,
) -> tuple[list[dict[str, Any]], SeedInspectionSummary]:
    included: list[dict[str, Any]] = []
    seen_candidates: dict[tuple[float, float], tuple[str, str]] = {}
    source_summaries: list[SeedSourceSummary] = []

    for source in sources:
        summary = SeedSourceSummary(
            source_campaign_id=source.campaign_id,
            source_export_path=str(source.export_path),
        )
        with source.export_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                summary.total_rows += 1
                result_id = str(row.get("result_id") or "")
                candidate = {
                    "Ethanol": float(row["param_Ethanol"]),
                    "SDS": float(row["param_SDS"]),
                }
                angle = float(row["obj_static_contact_angle"])
                exclusion_reasons = _exclusion_reasons(candidate, angle)
                if exclusion_reasons:
                    summary.excluded_rows += 1
                    summary.excluded_result_ids.append(
                        SeedRowDetail(result_id=result_id, reason=";".join(exclusion_reasons))
                    )
                    continue

                summary.valid_rows += 1
                candidate_key = _candidate_key(candidate)
                if candidate_key in seen_candidates:
                    summary.duplicate_rows += 1
                    duplicate_campaign_id, duplicate_result_id = seen_candidates[candidate_key]
                    summary.excluded_result_ids.append(
                        SeedRowDetail(
                            result_id=result_id,
                            reason=(
                                "duplicate_candidate"
                                f";kept_campaign_id={duplicate_campaign_id}"
                                f";kept_result_id={duplicate_result_id}"
                            ),
                        )
                    )
                    continue

                seen_candidates[candidate_key] = (source.campaign_id, result_id)
                summary.seeded_rows += 1
                included.append(
                    {
                        "parameter_values": candidate,
                        "objective_values": {"static_contact_angle": angle},
                        "metadata": {
                            "experiment_id": f"seed-{source.campaign_id}-{result_id}",
                            "notes": (
                                "Seeded from prior campaign "
                                f"{source.campaign_id} result {result_id}"
                            ),
                            "conditions": {
                                "phase": "seed",
                                "source_campaign_id": source.campaign_id,
                                "source_result_id": result_id,
                                "source_suggestion_id": str(row.get("suggestion_id") or ""),
                                "source_created_at": str(row.get("created_at") or ""),
                            },
                        },
                    }
                )
        source_summaries.append(summary)

    summary = SeedInspectionSummary(
        combined_seeded_rows=len(included),
        combined_valid_rows=sum(item.valid_rows for item in source_summaries),
        combined_excluded_rows=sum(item.excluded_rows for item in source_summaries),
        combined_duplicate_rows=sum(item.duplicate_rows for item in source_summaries),
        sources=source_summaries,
    )
    return included, summary


def _exclusion_reasons(candidate: dict[str, float], angle: float) -> list[str]:
    reasons: list[str] = []
    if not all(math.isfinite(value) for value in (*candidate.values(), angle)):
        reasons.append("non_finite_value")
    if math.isclose(angle, PENALTY_ANGLE_DEG, rel_tol=0.0, abs_tol=1e-9):
        reasons.append("penalty_objective")
    if not _in_bounds(candidate):
        reasons.append("outside_updated_search_space")
    return reasons

