from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


def write_json(path: str | Path, payload: Dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def render_results_table(results: List[Dict]) -> str:
    headers = [
        "eval",
        "status",
        "surface_response",
        "raw_response",
        "x_1",
        "x_2",
        "x_3",
        "x_4",
        "x_5",
        "x_6",
    ]
    lines = [" | ".join(headers), " | ".join(["---"] * len(headers))]
    for row in results:
        params = row["parameter_values"]
        obj = row.get("objective_values", {}).get("surface_response")
        values = [
            str(row["evaluation_index"]),
            row["status"],
            "" if obj is None else f"{obj:.6f}",
            "" if row.get("raw_response") is None else f"{row['raw_response']:.6f}",
            *(f"{params[f'x_{i}']:.6f}" for i in range(1, 7)),
        ]
        lines.append(" | ".join(values))
    return "\n".join(lines)
