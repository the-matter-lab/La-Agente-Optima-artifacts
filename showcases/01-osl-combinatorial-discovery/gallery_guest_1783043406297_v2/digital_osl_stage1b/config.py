from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAMPAIGN_SLUG = "digital_osl_stage1b"
DEFAULT_ARTIFACT_ROOT = Path("artifacts") / CAMPAIGN_SLUG
LEGACY_CAMPAIGN_ID = "03cd5601-f16d-4e76-a588-7d15bf8268cb"
LEGACY_EXPORT_CSV = Path("artifacts") / "digital_osl_stage1" / "20260703T031540Z_execute" / "campaign_export.csv"
ORIGINAL_STAGE1_ACTIVE_IDS = {
    "cap": ["A014", "A042", "A041", "A031", "A015", "A039"],
    "bridge": ["B065", "B066", "B067", "B056", "B057", "B037"],
    "core": ["C069", "C094", "C115", "C025", "C070", "C078", "C100", "C080", "C036", "C041"],
}


@dataclass
class Stage1bConfig:
    cap_catalog: Path = Path("adk9227_data_s1.csv")
    bridge_catalog: Path = Path("adk9227_data_s2.csv")
    core_catalog: Path = Path("adk9227_data_s3.csv")
    validation_catalog: Path = Path("adk9227_data_s6.csv")
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    execute: bool = False
    validate_with_bo_api: bool = True
    campaign_id: str | None = None
    campaign_name: str = "digital-osl-stage1b"
    campaign_description: str = (
        "Stage 1b digital OSL campaign with a deterministic frontier-aware expansion of the original "
        "Stage 1 fragment space. Uses imported Stage 1 observations plus CREST/GFN-FF and cheap "
        "TDDFT/PBE/def2-SVP evaluation without geometry optimization or frequency validation."
    )
    backend: str = "baybe"
    allow_plain_categorical_fallback: bool = False
    random_seed: int = 9227
    batch_size: int = 1
    cap_target: int = 12
    bridge_target: int = 12
    core_target: int = 18
    legacy_campaign_id: str = LEGACY_CAMPAIGN_ID
    legacy_export_csv: Path = LEGACY_EXPORT_CSV
    expected_legacy_successes: int = 16
    skip_legacy_import: bool = False
    max_new_bo_successes: int = 30
    max_runtime_minutes: int = 1440
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

    def materialize(self) -> "Stage1bConfig":
        clone = Stage1bConfig(**asdict(self))
        clone.cap_catalog = Path(clone.cap_catalog)
        clone.bridge_catalog = Path(clone.bridge_catalog)
        clone.core_catalog = Path(clone.core_catalog)
        clone.validation_catalog = Path(clone.validation_catalog)
        clone.artifact_root = Path(clone.artifact_root)
        clone.legacy_export_csv = Path(clone.legacy_export_csv)
        if clone.cap_target <= len(ORIGINAL_STAGE1_ACTIVE_IDS["cap"]):
            raise ValueError("cap_target must be greater than the original Stage 1 cap count (6)")
        if clone.bridge_target <= len(ORIGINAL_STAGE1_ACTIVE_IDS["bridge"]):
            raise ValueError("bridge_target must be greater than the original Stage 1 bridge count (6)")
        if clone.core_target <= len(ORIGINAL_STAGE1_ACTIVE_IDS["core"]):
            raise ValueError("core_target must be greater than the original Stage 1 core count (10)")
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
        for key in [
            "cap_catalog",
            "bridge_catalog",
            "core_catalog",
            "validation_catalog",
            "artifact_root",
            "legacy_export_csv",
        ]:
            payload[key] = str(payload[key])
        payload["artifact_dir"] = str(self.artifact_dir)
        return payload


@dataclass
class PreparedStage1b:
    config: Stage1bConfig
    cap_catalog: Any
    bridge_catalog: Any
    core_catalog: Any
    validation_report: dict[str, Any]
    active_caps: Any
    active_bridges: Any
    active_cores: Any
    candidate_library: Any
    legacy_import_rows: list[dict[str, Any]] = field(default_factory=list)
    legacy_import_summary: dict[str, Any] = field(default_factory=dict)
    intake: dict[str, Any] = field(default_factory=dict)
    intake_backend: str = ""
    preview_summary: dict[str, Any] = field(default_factory=dict)
