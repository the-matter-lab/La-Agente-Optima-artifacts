from __future__ import annotations

import csv
import json
from pathlib import Path

OBJ = ["donor_homo_error", "gap_error", "steric_excess", "heavy_atom_count"]


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pareto_flags(records: list[dict]) -> dict[str, bool]:
    good = [r for r in records if r.get("status") == "success"]
    flags = {}
    for a in good:
        av = a["objectives"]
        dominated = False
        for b in good:
            if a is b:
                continue
            bv = b["objectives"]
            if all(bv[o] <= av[o] for o in OBJ) and any(bv[o] < av[o] for o in OBJ):
                dominated = True
                break
        flags[a["candidate_id"]] = not dominated
    return flags


def _score(row: dict, mins: dict[str, float], maxs: dict[str, float]) -> float:
    total = 0.0
    for o in OBJ:
        span = max(maxs[o] - mins[o], 1e-12)
        total += (row["objectives"][o] - mins[o]) / span
    return total


def write_report(records_path: Path, report_md: Path, report_csv: Path) -> None:
    records = _records(records_path)
    successes = [r for r in records if r.get("status") == "success"]
    failed = [r for r in records if r.get("status") != "success"]
    flags = pareto_flags(records)
    if successes:
        mins = {o: min(r["objectives"][o] for r in successes) for o in OBJ}
        maxs = {o: max(r["objectives"][o] for r in successes) for o in OBJ}
        ranked = sorted(successes, key=lambda r: (not flags.get(r["candidate_id"], False), _score(r, mins, maxs)))
    else:
        ranked = []
    representative = ranked[:10]
    with report_csv.open("w", newline="") as f:
        fieldnames = [
            "candidate_id", "R1", "R2", "R3", "ligand_smiles", "phase", "status", "pareto", "representative_tradeoff",
            "homo_energy_eV", "lumo_energy_eV", "homo_lumo_gap_eV", "phosphorus_partial_charge", "molecular_volume_ang3", "heavy_atom_count",
            *OBJ, "error",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        rep_ids = {r["candidate_id"] for r in representative}
        for r in successes + failed:
            desc = r.get("descriptors") or {}
            obj = r.get("objectives") or {}
            w.writerow({
                **{k: r.get(k, "") for k in ["candidate_id", "R1", "R2", "R3", "ligand_smiles", "phase", "status", "error"]},
                "pareto": flags.get(r.get("candidate_id"), False),
                "representative_tradeoff": r.get("candidate_id") in rep_ids,
                **{k: desc.get(k, "") for k in ["homo_energy_eV", "lumo_energy_eV", "homo_lumo_gap_eV", "phosphorus_partial_charge", "molecular_volume_ang3", "heavy_atom_count"]},
                **{k: obj.get(k, "") for k in OBJ},
            })
    initial_ids = {r["candidate_id"] for r in successes if r.get("phase") == "warm_start"}
    bo_pareto = [r for r in successes if r.get("phase") == "bo" and flags.get(r["candidate_id"])]
    init_pareto = [r for r in successes if r["candidate_id"] in initial_ids and flags.get(r["candidate_id"])]
    trend_rows = representative or successes[:10]
    labels = [g for r in trend_rows for g in [r.get("R1"), r.get("R2"), r.get("R3")] if g]
    trend = ", ".join(f"{g}:{labels.count(g)}" for g in sorted(set(labels))) if labels else "not enough successful records"
    lines = [
        "# Phosphine electronic-tuning BO report",
        "",
        "## Multi-objective strategy",
        "Finite discrete `candidate_id` categorical campaign using BO-MCP with Pareto scalarization and hypervolume-improvement acquisition where supported. The evaluator submits raw transformed objectives, so post-warm-start proposals are based on measured HOMO-target error, gap-target error, steric excess, and heavy-atom count rather than LLM chemical judgement.",
        "",
        f"Successful evaluations in this artifact: {len(successes)}; failed evaluations: {len(failed)}.",
        f"Observed Pareto-front size: {sum(flags.values())}.",
        f"BO-discovered Pareto members after warm start: {len(bo_pareto)}. Initial-design Pareto members still present: {len(init_pareto)}.",
        "",
        "## Representative trade-off ligands (up to 10)",
    ]
    for r in representative:
        d = r["descriptors"]
        lines.append(
            f"- {r['candidate_id']} {r['R1']}/{r['R2']}/{r['R3']} pareto={flags.get(r['candidate_id'], False)} "
            f"HOMO={d['homo_energy_eV']:.3f} eV gap={d['homo_lumo_gap_eV']:.3f} eV "
            f"P_charge={d['phosphorus_partial_charge']:.3f} volume={d['molecular_volume_ang3']:.1f} A^3 heavy={d['heavy_atom_count']}"
        )
    lines += [
        "",
        "## Failed candidates",
    ]
    if failed:
        lines += [f"- {r.get('candidate_id')}: {r.get('error')}" for r in failed]
    else:
        lines.append("- None recorded in this artifact.")
    lines += [
        "",
        "## Initial-design improvement check",
        "BO improved the observed front/trade-off set if at least one `phase=bo` row is marked Pareto or representative in `report.csv`; inspect the CSV for the definitive row-level status.",
        "",
        "## Substituent trend summary near the current trade-off set",
        f"Representative substituent counts: {trend}. Interpret phosphorus charge together with HOMO: less negative HOMO values and less positive/more negative P charges both indicate stronger donor character, but no standalone P-charge target was imposed.",
    ]
    report_md.write_text("\n".join(lines) + "\n")
