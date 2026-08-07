"""Objective extraction + reporting for the direct-arylation-yield campaign.

The JSONL artifact written here is append-only provenance for humans/logs
only: the optimization loop must never read it back to decide whether to
continue. The authoritative final report is built from BO-MCP's own
suggestion + result rows (`build_summary`), which is server truth.
"""
import json
import os

from .intake import OBJECTIVE_NAME


def append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def _conditions(params: dict) -> str:
    return (f"base={params.get('base')!r} ligand={params.get('ligand')!r} "
            f"solvent={params.get('solvent')!r} concentration={params.get('concentration')} "
            f"temperature_c={params.get('temperature_c')}")


def print_attempt(attempt_no: int, budget: int, status: str, params: dict,
                   yield_value, error: str | None = None) -> None:
    cond = _conditions(params)
    if status == "success":
        print(f"[RESULT] attempt={attempt_no}/{budget} status=success "
              f"yield={yield_value:.3f}percent {cond}", flush=True)
    else:
        print(f"[ALERT] attempt={attempt_no}/{budget} status=failed "
              f"error={error!r} {cond}", flush=True)


def build_summary(client, campaign_id: str) -> dict:
    """Read the server's suggestion + result rows and produce the final report."""
    suggestions = client.query_suggestions(campaign_id, limit=500)
    results = client.get_results(campaign_id)
    results_by_suggestion = {r.get("suggestion_id"): r for r in results if r.get("suggestion_id")}

    candidates = []
    for s in suggestions:
        status = s.get("status")
        if status == "pending":
            continue
        params = s.get("parameter_values") or {}
        result = results_by_suggestion.get(s.get("suggestion_id"))
        if result is not None:
            objective_values = result.get("objective_values") or {}
            candidates.append({
                "suggestion_id": s.get("suggestion_id"),
                "parameters": params,
                "status": "success",
                "yield_percent": objective_values.get(OBJECTIVE_NAME),
            })
        else:
            candidates.append({
                "suggestion_id": s.get("suggestion_id"),
                "parameters": params,
                "status": status,
                "yield_percent": None,
            })

    successes = [c for c in candidates if c["status"] == "success" and c["yield_percent"] is not None]
    best = max(successes, key=lambda c: c["yield_percent"], default=None)
    return {
        "campaign_id": campaign_id,
        "attempted": len(candidates),
        "successful": len(successes),
        "failed": len(candidates) - len(successes),
        "best_yield_percent": best["yield_percent"] if best else None,
        "best_conditions": best["parameters"] if best else None,
        "candidates": candidates,
    }


def write_summary(path: str, summary: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(summary, fh, indent=2)


def print_summary(summary: dict) -> None:
    print(f"[RESULT] SUMMARY campaign_id={summary['campaign_id']} "
          f"attempted={summary['attempted']} successful={summary['successful']} "
          f"failed={summary['failed']} best_yield_percent={summary['best_yield_percent']} "
          f"best_conditions={summary['best_conditions']}", flush=True)
    for c in summary["candidates"]:
        y = f"{c['yield_percent']:.3f}percent" if c["yield_percent"] is not None else "n/a"
        print(f"[RESULT] candidate suggestion_id={c['suggestion_id']} status={c['status']} "
              f"yield={y} parameters={c['parameters']}", flush=True)
