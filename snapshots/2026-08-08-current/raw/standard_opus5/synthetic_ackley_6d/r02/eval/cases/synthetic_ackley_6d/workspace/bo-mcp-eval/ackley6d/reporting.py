"""Artifacts, tagged stdout, and the final report."""

import json
from pathlib import Path

import logfire

from .objective import OBJECTIVE_NAME
from .space import PARAM_NAMES

_LOG_PATH: Path | None = None


def set_log_path(path: Path) -> None:
    global _LOG_PATH
    _LOG_PATH = path
    path.parent.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    """Detail line: run log on disk only (not stdout)."""
    if _LOG_PATH is not None:
        with _LOG_PATH.open("a") as fh:
            fh.write(message.rstrip() + "\n")
    logfire.debug("{message}", message=message)



def emit(tag: str, message: str) -> None:
    """Tagged stdout line, also mirrored into the run log."""
    line = f"[{tag}] {message}"
    print(line, flush=True)
    log(line)



def append_row(path: Path, row: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def _fmt_params(params: dict) -> str:
    return " ".join(f"{float(params.get(n, float('nan'))):.4f}" for n in PARAM_NAMES)


def result_line(row: dict) -> str:
    if row["status"] == "success":
        return (
            f"#{row['evaluation_index']:02d} status=success "
            f"{OBJECTIVE_NAME}={row['objective_values'][OBJECTIVE_NAME]:.6f} "
            f"raw_response={row['raw_response']:.6f} | x=[{_fmt_params(row['parameter_values'])}]"
        )
    return (
        f"#{row['evaluation_index']:02d} status={row['status']} "
        f"reason={row['failure_reason']} | x=[{_fmt_params(row['parameter_values'])}]"
    )


def render_table(rows: list[dict]) -> str:
    head = (
        f"{'idx':>4}  {'status':<8}  {OBJECTIVE_NAME:>17}  {'raw_response':>13}  "
        + "  ".join(f"{n:>7}" for n in PARAM_NAMES)
    )
    lines = [head, "-" * len(head)]
    for r in rows:
        obj = r["objective_values"][OBJECTIVE_NAME] if r["status"] == "success" else None
        raw = r.get("raw_response")
        obj_s = f"{obj:.6f}" if obj is not None else "-"
        raw_s = f"{raw:.6f}" if raw is not None else "-"
        coords = "  ".join(
            f"{float(r['parameter_values'].get(n, float('nan'))):7.4f}" for n in PARAM_NAMES
        )
        lines.append(
            f"{r['evaluation_index']:>4}  {r['status']:<8}  {obj_s:>17}  {raw_s:>13}  {coords}"
        )

    return "\n".join(lines)


def finalize(artifacts_dir: Path, campaign_id: str, rows: list[dict], attempted: int) -> dict:
    ok = [r for r in rows if r["status"] == "success"]
    best = max(ok, key=lambda r: r["objective_values"][OBJECTIVE_NAME]) if ok else None
    summary = {
        "campaign_id": campaign_id,
        "attempted_evaluations": attempted,
        "successful_evaluations": len(ok),
        "failed_evaluations": attempted - len(ok),
        "best": None,
    }
    if best is not None:
        summary["best"] = {
            "evaluation_index": best["evaluation_index"],
            "parameter_values": {n: float(best["parameter_values"][n]) for n in PARAM_NAMES},
            "surface_response": best["objective_values"][OBJECTIVE_NAME],
            "raw_response": best["raw_response"],
        }
    (artifacts_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (artifacts_dir / "results_table.txt").write_text(render_table(rows) + "\n")

    emit("RESULT", "=" * 72)
    emit("RESULT", f"campaign_id={campaign_id}")
    emit(
        "RESULT",
        f"evaluations: attempted={attempted} successful={len(ok)} "
        f"failed={summary['failed_evaluations']}",
    )
    if best is not None:
        b = summary["best"]
        coords = ", ".join(f"{n}={b['parameter_values'][n]:.6f}" for n in PARAM_NAMES)
        emit("RESULT", f"best coordinates (normalized): {coords}")
        emit("RESULT", f"best raw_response      = {b['raw_response']:.6f}")
        emit("RESULT", f"best surface_response  = {b['surface_response']:.6f}")
    else:
        emit("ALERT", "no successful evaluations recorded")
    emit("RESULT", "candidate table:")
    for line in render_table(rows).splitlines():
        emit("RESULT", line)
    emit("RESULT", f"artifacts: {artifacts_dir}")
    emit("RESULT", "=" * 72)
    return summary
