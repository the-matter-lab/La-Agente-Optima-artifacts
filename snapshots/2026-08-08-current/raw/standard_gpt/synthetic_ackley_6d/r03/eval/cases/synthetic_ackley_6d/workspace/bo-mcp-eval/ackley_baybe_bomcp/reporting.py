from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping

from .search_space import PARAMETER_NAMES


BASE_ARTIFACT_DIR = Path("artifacts") / "ackley_baybe_bomcp"


def artifact_dir_for_campaign(campaign_id: str) -> Path:
    return BASE_ARTIFACT_DIR / campaign_id


def ensure_artifact_dir(campaign_id: str) -> Path:
    artifact_dir = artifact_dir_for_campaign(campaign_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True) + "\n")


def write_rows_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    fieldnames = [
        "evaluation_index",
        *PARAMETER_NAMES,
        "surface_response",
        "raw_response",
        "status",
        "failure_reason",
        "suggestion_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            parameter_values = dict(row.get("parameter_values", {}))
            objective_values = dict(row.get("objective_values", {}))
            writer.writerow(
                {
                    "evaluation_index": row.get("evaluation_index"),
                    **{name: parameter_values.get(name) for name in PARAMETER_NAMES},
                    "surface_response": objective_values.get("surface_response"),
                    "raw_response": row.get("raw_response"),
                    "status": row.get("status"),
                    "failure_reason": row.get("failure_reason", ""),
                    "suggestion_id": row.get("suggestion_id", ""),
                }
            )


def write_markdown_report(path: Path, summary: Mapping[str, object], rows: list[Mapping[str, object]]) -> None:
    best_parameters = summary.get("best_parameter_values") or {}
    table_lines = [
        "| evaluation_index | status | surface_response | raw_response | failure_reason | x_1 | x_2 | x_3 | x_4 | x_5 | x_6 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        parameter_values = dict(row.get("parameter_values", {}))
        objective_values = dict(row.get("objective_values", {}))
        table_lines.append(
            "| {evaluation_index} | {status} | {surface_response} | {raw_response} | {failure_reason} | {x_1} | {x_2} | {x_3} | {x_4} | {x_5} | {x_6} |".format(
                evaluation_index=row.get("evaluation_index", ""),
                status=row.get("status", ""),
                surface_response=objective_values.get("surface_response", ""),
                raw_response=row.get("raw_response", ""),
                failure_reason=row.get("failure_reason", ""),
                **{name: parameter_values.get(name, "") for name in PARAMETER_NAMES},
            )
        )

    content = "\n".join(
        [
            "# Ackley 6D BO-MCP Campaign Report",
            "",
            f"- campaign_id: {summary.get('campaign_id', '')}",
            f"- attempted_evaluations: {summary.get('attempted_evaluations', 0)}",
            f"- successful_evaluations: {summary.get('successful_evaluations', 0)}",
            f"- best_surface_response: {summary.get('best_surface_response', '')}",
            f"- best_raw_response: {summary.get('best_raw_response', '')}",
            f"- best_parameter_values: {json.dumps(best_parameters, sort_keys=True)}",
            "",
            "## Evaluated Candidates",
            "",
            *table_lines,
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
