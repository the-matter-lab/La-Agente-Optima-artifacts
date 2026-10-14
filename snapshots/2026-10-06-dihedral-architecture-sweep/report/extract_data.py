"""Extract per-repeat records for the 2026-10-06b dihedral sweep (commit 0949c2d1).

Reads only the immutable run tree and writes data/runs.json. Run with the orchestrator
environment (numpy).
"""

import glob
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path("/local-scratch/home/lynnfang00/research/dihedral-runs-sweep-2026-10-06b")
OUT = Path(__file__).parent / "data"
HARTREE_TO_KCAL = 627.509474
ARMS = {
    "main_agent_script_bo_mcp": "Main-script",
    "main_agent_script_no_bo_mcp": "Local-BO",
    "standard_subagent_script_bo_mcp": "Standard",
    "main_agent_tool_passing_bo_mcp": "Tool-loop",
}


def canonical(params: dict) -> dict:
    """Map each run's own parameter names onto C-C-C-C, C-C-C-O and C-C-O-H.

    Names spell atoms (cccc, occc, hocc, c3_c4_o_h, ...) or, in two runs, are numbered
    1/2/3; both of those runs define 1 = C-C-C-C, 2 = C-C-C-O, 3 = C-C-O-H in their
    final answers.
    """
    out = {}
    for name, value in params.items():
        key = name.lower()
        atoms = re.sub(r"[^a-z]", "", re.sub(r"(dihedral|dih|deg|tau\d*|phi\d*)", "", key))
        if not atoms:
            atoms = {"1": "cccc", "2": "ccco", "3": "ccoh"}[re.search(r"(\d)", key).group(1)]
        if "h" in atoms:
            slot = "ccoh"
        elif "o" in atoms:
            slot = "ccco"
        elif set(atoms) == {"c"}:
            slot = "cccc"
        else:
            raise ValueError(name)
        assert slot not in out, (name, params)
        out[slot] = value
    assert set(out) == {"cccc", "ccco", "ccoh"}, params
    return out


def tool_category(name: str) -> str:
    if name.startswith("bo_"):
        return "BO-MCP tools"
    if name.startswith("container_"):
        return "Container tools"
    if name in {"bash_exec", "execute", "run_python", "python_repl", "start_monitor", "read_monitor", "list_monitors", "stop_monitor"} or "bash" in name or "python" in name or "monitor" in name:
        return "Host shell / Python"
    if name in {"task", "delegate", "run_subagent"} or "subagent" in name or name == "task":
        return "Subagent delegation"
    return "Other (files, skills, geometry, search)"


records = []
for manifest_path in sorted(ROOT.glob("dihedral_*Z/repeat_*/run_manifest.json")):
    repeat_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    metrics = json.loads((repeat_dir / "cases/dihedral/metrics.json").read_text())
    output = json.loads((repeat_dir / "cases/dihedral/output.json").read_text())
    mode = manifest["eval"]["architecture_mode"]
    source = metrics["local_artifacts"] if mode == "main_agent_script_no_bo_mcp" else metrics["bo_mcp"]
    vectors = sorted(source["objective_vectors"], key=lambda v: v["evaluation_index"])
    energies = [next(iter(v["objective_values"].values())) for v in vectors]
    params = [canonical(v["parameter_values"]) for v in vectors]
    agent = metrics["agent"]
    arch = metrics["architecture"]
    split = metrics.get("usage_split") or {}
    tools = arch.get("tool_call_counts_by_name") or {}
    categories: dict[str, int] = {}
    for name, count in tools.items():
        categories[tool_category(name)] = categories.get(tool_category(name), 0) + count
    records.append(
        {
            "arm": ARMS[mode],
            "mode": mode,
            "repeat": int(repeat_dir.name.split("_")[1]),
            "run_dir": str(repeat_dir.relative_to(ROOT.parent)),
            "commit": manifest["git"]["sha"],
            "energies": energies,
            "params": params,
            "best_so_far": source["best_so_far_by_evaluation"],
            "best": source["best_objective_value"],
            "best_index": source["best_objective_evaluation_index"],
            "best_params": canonical(source["best_parameters"]),
            "attempted": source["attempted_objective_evaluations"],
            "failed": source.get("failed_evaluations"),
            "duplicates": source.get("duplicate_evaluations"),
            "cost_usd": agent["cost_usd"],
            "input_tokens": agent["input_tokens"],
            "cache_read_tokens": agent["cache_read_tokens"],
            "output_tokens": agent["output_tokens"],
            "reasoning_tokens": agent["reasoning_tokens"],
            "requests": agent["request_count"],
            "tool_calls": agent["tool_call_count"],
            "runtime_s": agent["runtime_s"],
            "tool_categories": categories,
            "tool_counts": tools,
            "subagent_delegations": arch.get("subagent_delegation_count"),
            "script_artifacts": arch.get("script_artifact_count"),
            "usage_split": {"main": {k: (split.get("main") or {}).get(k) for k in ("cost_usd", "request_count")}},
            "campaign_batch_size": source.get("campaign_batch_size"),
            "campaign_iterations": source.get("campaign_iteration"),
            "campaign_initial_design": source.get("campaign_initial_design_size"),
            "suggestions_generated": source.get("suggestions_generated"),
            "clean": metrics["benchmark"]["benchmark_clean"],
            "provenance": metrics["provenance"]["verification_status"],
            "trace_id": output.get("trace_id") or (re.search(r'"trace_id": ?"([0-9a-f]{32})"', (repeat_dir / "cases/dihedral/output.json").read_text()) or [None, None])[1],
        }
    )

OUT.mkdir(exist_ok=True)
(OUT / "runs.json").write_text(json.dumps(records, indent=1))
for r in records:
    assert len(r["energies"]) == 60 and r["commit"].startswith("0949c2d1"), r["run_dir"]
print(len(records), "runs written")
for r in sorted(records, key=lambda r: (r["arm"], r["repeat"])):
    print(f"{r['arm']:12s} r{r['repeat']} best {r['best']:.6f} @{r['best_index']:>2} first {r['energies'][0]:.6f} "
          f"cost ${r['cost_usd']:.2f} req {r['requests']} tools {r['tool_calls']} rt {r['runtime_s']:.0f}s dup {r['duplicates']} failed {r['failed']} "
          f"batch {r['campaign_batch_size']} iters {r['campaign_iterations']} cats {r['tool_categories']}")
