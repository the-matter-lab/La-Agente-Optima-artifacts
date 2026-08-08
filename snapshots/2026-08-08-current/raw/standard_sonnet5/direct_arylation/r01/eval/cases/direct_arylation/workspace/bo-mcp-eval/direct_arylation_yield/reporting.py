"""Append-only provenance artifact + tagged console reporting.

The JSONL artifact is provenance for reporting only: the optimization loop
must never read it back to decide whether to continue (BO-MCP's
next_action/get_results own that decision). It is read back once, at process
startup, purely to recover the count of previously *failed* attempts (which
BO-MCP does not persist) so a resumed invocation does not exceed the overall
attempt budget.
"""
import json
import os


def append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def print_result_line(record: dict) -> None:
    p = record["parameter_values"]
    cond = (f"base={p.get('base')!r} ligand={p.get('ligand')!r} solvent={p.get('solvent')!r} "
            f"concentration={p.get('concentration')} temperature_c={p.get('temperature_c')}")
    if record["status"] == "success":
        print(f"[RESULT] status=success yield={record['yield']:.3f}percent {cond} "
              f"suggestion_id={record.get('suggestion_id')}", flush=True)
    else:
        print(f"[RESULT] status=failed error={record.get('error')!r} {cond} "
              f"suggestion_id={record.get('suggestion_id')}", flush=True)


def build_summary(campaign_id: str, records: list) -> dict:
    successes = [r for r in records if r["status"] == "success"]
    best = max(successes, key=lambda r: r["yield"], default=None)
    return {
        "campaign_id": campaign_id,
        "attempted": len(records),
        "successful": len(successes),
        "failed": len(records) - len(successes),
        "best_yield_percent": best["yield"] if best else None,
        "best_conditions": best["parameter_values"] if best else None,
        "candidates": records,
    }


def write_summary(path: str, summary: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(summary, fh, indent=2)
