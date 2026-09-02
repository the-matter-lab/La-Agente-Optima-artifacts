from __future__ import annotations

import json
import math
from pathlib import Path

import pormake as pm

from .search_space import _edge_length, build_space


def encode_candidate(topology: str, node: str, edge: str) -> str:
    return f"{topology}|{node}|{edge}"


def decode_candidate(candidate_id: str) -> dict[str, str]:
    topology, node, edge = candidate_id.split("|", 2)
    return {"topology": topology, "node": node, "edge": edge}


def load_prior_evaluations(prior_artifact_dir: str | Path) -> list[dict]:
    path = Path(prior_artifact_dir) / "evaluations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _balanced_score(row: dict) -> float:
    obj = row.get("objectives", {})
    sel = float(obj.get("selectivity_proxy", 0.0))
    cap = min(float(obj.get("capacity_proxy", 0.0)) / 10.0, 1.0)
    return 0.6 * sel + 0.4 * cap


def _neighbor_edges(edge_ids: set[str], *, neighbors_each_side: int = 2, max_edges: int = 18) -> list[dict]:
    db = pm.Database()
    rows = sorted((_edge_length(db.get_bb(eid)), eid) for eid in db.bb_list if eid.startswith("E") and db.get_bb(eid).is_edge)
    positions = {eid: i for i, (_, eid) in enumerate(rows)}
    lengths = {eid: length for length, eid in rows}
    chosen = set(edge_ids)
    for eid in list(edge_ids):
        if eid not in positions:
            continue
        i = positions[eid]
        for j in range(max(0, i - neighbors_each_side), min(len(rows), i + neighbors_each_side + 1)):
            chosen.add(rows[j][1])
    if len(chosen) > max_edges:
        seeds = sorted((eid for eid in edge_ids if eid in lengths), key=lambda eid: lengths[eid])
        if len(seeds) >= max_edges:
            chosen = set(seeds[:max_edges])
        else:
            extras = sorted(chosen - set(seeds), key=lambda eid: lengths[eid])
            slots = max_edges - len(seeds)
            idxs = sorted({round(i * (len(extras) - 1) / max(1, slots - 1)) for i in range(slots)}) if extras else []
            chosen = set(seeds) | {extras[i] for i in idxs}
    return [{"id": eid, "length": lengths[eid]} for eid in sorted(chosen, key=lambda eid: lengths.get(eid, 0.0)) if eid in lengths]


def build_refined_space(
    prior_artifact_dir: str | Path,
    *,
    node_limit_per_topology: int = 6,
    edge_limit: int = 18,
    min_seed_balance: float = 0.0,
) -> dict:
    prior_rows = load_prior_evaluations(prior_artifact_dir)
    successful = [r for r in prior_rows if r.get("ok") and math.isfinite(_balanced_score(r))]
    successful.sort(key=_balanced_score, reverse=True)

    base_path = Path(prior_artifact_dir) / "candidate_space.json"
    if base_path.exists():
        base = json.loads(base_path.read_text())
    else:
        base = build_space(node_limit_per_topology=node_limit_per_topology, edge_limit=10)

    # Prior success identified pcu as the validated family; keep compatible pcu nodes and
    # expand only along edge length neighborhoods near prior good trade-off edges.
    topologies = sorted({r["parameters"]["topology"] for r in successful}) or base["topologies"][:1]
    compatible_nodes = {}
    for topo in topologies:
        seed_nodes = [r["parameters"]["node"] for r in successful if r["parameters"]["topology"] == topo]
        ranked = [row["id"] for row in base["compatible_nodes"].get(topo, [])]
        merged = []
        for node in seed_nodes + ranked:
            if node not in merged:
                merged.append(node)
        compatible_nodes[topo] = merged[:node_limit_per_topology]

    good_edges = {
        r["parameters"]["edge"]
        for r in successful
        if _balanced_score(r) >= min_seed_balance and float(r["objectives"].get("selectivity_proxy", 0.0)) >= 0.25
    }
    if not good_edges:
        good_edges = {e["id"] for e in base.get("edge_metadata", [])[: min(10, edge_limit)]}
    edges = _neighbor_edges(good_edges, max_edges=edge_limit)

    triples = []
    for topo in topologies:
        for node in compatible_nodes.get(topo, []):
            for edge in [e["id"] for e in edges]:
                triples.append({"candidate_id": encode_candidate(topo, node, edge), "topology": topo, "node": node, "edge": edge})

    seed_rows = []
    candidate_ids = {t["candidate_id"] for t in triples}
    for row in successful:
        cid = encode_candidate(row["parameters"]["topology"], row["parameters"]["node"], row["parameters"]["edge"])
        if cid not in candidate_ids:
            triples.append({"candidate_id": cid, **row["parameters"]})
            candidate_ids.add(cid)
        seed_rows.append({"candidate_id": cid, "source_row": row, "balance_score": _balanced_score(row)})

    final_edges = sorted({t["edge"] for t in triples})
    edge_lengths = {e["id"]: e["length"] for e in edges}
    return {
        "mode": "refined_candidate_id",
        "prior_artifact_dir": str(prior_artifact_dir),
        "topologies": topologies,
        "compatible_nodes": compatible_nodes,
        "edges": final_edges,
        "edge_metadata": [{"id": eid, "length": edge_lengths.get(eid)} for eid in final_edges],
        "candidates": sorted(triples, key=lambda r: r["candidate_id"]),
        "candidate_ids": sorted(candidate_ids),
        "seed_rows": seed_rows,
        "prior_success_count": len(successful),
        "prior_total_count": len(prior_rows),
    }
