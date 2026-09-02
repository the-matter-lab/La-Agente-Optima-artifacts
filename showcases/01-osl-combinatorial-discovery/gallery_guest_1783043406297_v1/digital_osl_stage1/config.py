from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAMPAIGN_SLUG = "digital_osl_stage1"
DEFAULT_ARTIFACT_ROOT = Path("artifacts") / CAMPAIGN_SLUG


@dataclass
class Stage1Config:
    cap_catalog: Path = Path("adk9227_data_s1.csv")
    bridge_catalog: Path = Path("adk9227_data_s2.csv")
    core_catalog: Path = Path("adk9227_data_s3.csv")
    validation_catalog: Path = Path("adk9227_data_s6.csv")
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    execute: bool = False
    validate_with_bo_api: bool = True
    campaign_id: str | None = None
    campaign_name: str = "digital-osl-stage1"
    campaign_description: str = (
        "Stage 1 bounded, cheap, first-pass digital OSL campaign over fragment-assembled "
        "A-B-C-B-A molecules. Uses CREST/GFN-FF plus cheap TDDFT/PBE/def2-SVP without "
        "geometry optimization or frequency validation."
    )
    backend: str = "baybe"
    allow_plain_categorical_fallback: bool = False
    random_seed: int = 9227
    batch_size: int = 1
    cap_limit: int = 6
    bridge_limit: int = 6
    core_limit: int = 10
    initial_observation_count: int = 4
    seed_diversity_pool: int = 4
    max_successful_evaluations: int = 6
    max_runtime_minutes: int = 180
    target_energy_ev: float = 2.65
    low_state_window: int = 5
    ambiguity_window_kcal: float = 2.0
    tddft_nstates: int = 6
    basis_set: str = "def2-SVP"
    xc_functional: str = "PBE"
    crest_method: str = "gfnff"
    crest_threads: int = 8
    pyscf_timeout_s: int = 900
    evaluation_timeout_s: int = 1200
    evaluation_backend: str = "digital"
    terminate_on_exit: bool = False
    export_format: str = "csv"
    run_label: str | None = None

    def materialize(self) -> "Stage1Config":
        clone = Stage1Config(**asdict(self))
        clone.cap_catalog = Path(clone.cap_catalog)
        clone.bridge_catalog = Path(clone.bridge_catalog)
        clone.core_catalog = Path(clone.core_catalog)
        clone.validation_catalog = Path(clone.validation_catalog)
        clone.artifact_root = Path(clone.artifact_root)
        if not clone.run_label:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            mode = "execute" if clone.execute else "preview"
            clone.run_label = f"{timestamp}_{mode}"
        return clone

    @property
    def artifact_dir(self) -> Path:
        if not self.run_label:
            raise ValueError("run_label is not materialized")
        return self.artifact_root / self.run_label

    def to_jsonable_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ["cap_catalog", "bridge_catalog", "core_catalog", "validation_catalog", "artifact_root"]:
            payload[key] = str(payload[key])
        payload["artifact_dir"] = str(self.artifact_dir)
        return payload


@dataclass
class PreparedStage:
    config: Stage1Config
    cap_catalog: Any
    bridge_catalog: Any
    core_catalog: Any
    validation_report: dict[str, Any]
    active_caps: Any
    active_bridges: Any
    active_cores: Any
    candidate_library: Any
    initial_candidates: list[dict[str, Any]]
    intake: dict[str, Any]
    intake_backend: str
    preview_summary: dict[str, Any] = field(default_factory=dict)
