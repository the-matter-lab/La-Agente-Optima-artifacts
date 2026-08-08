#!/usr/bin/env python3
"""Rebuild the paper-facing figures from the frozen report data."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPOSITORY_ROOT / "snapshots/2026-08-08-current"
REPORT = SNAPSHOT / "report"
BUILDER = REPORT / "control/build_final_report.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("benchmark_report_builder", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load report builder: {BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    data = json.loads((REPORT / "control/REPORT_DATA.json").read_text())
    builder = load_builder()
    builder.FIGURES = REPORT / "figures"
    builder.FIGURES.mkdir(parents=True, exist_ok=True)
    builder.all_observed_plot(data["standard_run_rows"])
    builder.quality_plot(data["trajectories"])
    builder.convergence_plot(data["trajectories"])
    builder.resource_plot(data["standard_arms"])
    builder.reliability_plot(data["standard_arms"])
    builder.architecture_quality_plot(data["gpt_architecture_run_rows"])
    builder.architecture_resource_plot(data["gpt_architecture_rows"])
    builder.architecture_convergence_plot(data["gpt_architecture_trajectories"])
    builder.architecture_auc_horizons_plot(data["gpt_architecture_trajectories"])
    builder.architecture_reliability_plot(data["gpt_architecture_run_rows"])
    builder.architecture_efficiency_plot(data["gpt_architecture_rows"])


if __name__ == "__main__":
    main()
