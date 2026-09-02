from __future__ import annotations

import logging
import math
from functools import lru_cache

import numpy as np
import pormake as pm

from domains.mofs.ontomofs import BuildingBlock, MOFBuilder, Topology

ALLOWED_TOPOLOGIES = ("pcu", "dia", "rtl", "ths", "bcu", "srs", "nbo", "tbo", "pts")


def _quiet_pormake() -> None:
    try:
        import pormake.log as pormake_log

        pormake_log.console_log_handler.setLevel(logging.CRITICAL)
    except Exception:
        pass


def _edge_length(pm_bb) -> float:
    lengths = getattr(pm_bb, "lengths", None)
    try:
        if lengths is not None and len(lengths):
            return float(np.mean(lengths))
    except Exception:
        pass
    pts = getattr(pm_bb, "connection_points", [])
    return float(np.linalg.norm(pts[0] - pts[1])) if len(pts) >= 2 else 0.0


def _pick_diverse_edges(edge_ids: list[str], limit: int) -> list[dict]:
    db = pm.Database()
    rows = sorted((_edge_length(db.get_bb(eid)), eid) for eid in edge_ids)
    if len(rows) <= limit:
        return [{"id": eid, "length": length} for length, eid in rows]
    idxs = sorted({round(i * (len(rows) - 1) / (limit - 1)) for i in range(limit)})
    return [{"id": rows[i][1], "length": rows[i][0]} for i in idxs]


@lru_cache(maxsize=1)
def build_space(node_limit_per_topology: int = 6, edge_limit: int = 10) -> dict:
    _quiet_pormake()
    db = pm.Database()
    builder = MOFBuilder()
    node_ids = [bid for bid in db.bb_list if bid.startswith("N") and db.get_bb(bid).is_node]
    edge_ids = [bid for bid in db.bb_list if bid.startswith("E") and db.get_bb(bid).is_edge]

    topologies: list[str] = []
    compatible_nodes: dict[str, list[dict]] = {}
    excluded: dict[str, str] = {}

    for topo_id in ALLOWED_TOPOLOGIES:
        topo = Topology.from_pormake_db_id(topo_id)
        node_types = [int(x) for x in topo.pm_topology.unique_node_types]
        node_degrees = [len(ls.positions) for ls in topo.pm_topology.unique_local_structures]
        rows = []
        for node_id in node_ids:
            pm_bb = db.get_bb(node_id)
            if len(pm_bb.connection_point_indices) != node_degrees[0]:
                continue
            bb = BuildingBlock.from_pormake_db_id(node_id)
            score = 0.0
            ok = True
            for nt, degree in zip(node_types, node_degrees):
                if len(pm_bb.connection_point_indices) != degree:
                    ok = False
                    break
                try:
                    score += float(builder.rmsd_for_node_type(topo, nt, bb))
                except Exception:
                    ok = False
                    break
            if ok and math.isfinite(score):
                rows.append({"id": node_id, "rmsd": score, "degree": node_degrees[0]})
        rows.sort(key=lambda r: (r["rmsd"], r["id"]))
        if rows:
            topologies.append(topo_id)
            compatible_nodes[topo_id] = rows[:node_limit_per_topology]
        else:
            excluded[topo_id] = "No single node building block can satisfy all unique node local structures."

    edges = _pick_diverse_edges(edge_ids, edge_limit)
    node_union = sorted({row["id"] for rows in compatible_nodes.values() for row in rows})
    return {
        "allowed_topologies": list(ALLOWED_TOPOLOGIES),
        "topologies": topologies,
        "nodes": node_union,
        "edges": [e["id"] for e in edges],
        "compatible_nodes": compatible_nodes,
        "edge_metadata": edges,
        "excluded_topologies": excluded,
    }


def is_compatible(space: dict, topology: str, node: str, edge: str) -> tuple[bool, str]:
    if topology not in space["topologies"]:
        return False, f"topology {topology!r} not in compatible single-node topology set"
    if node not in {r["id"] for r in space["compatible_nodes"].get(topology, [])}:
        return False, f"node {node!r} is not compatible with topology {topology!r}"
    if edge not in space["edges"]:
        return False, f"edge {edge!r} is not in selected PORMAKE edge set"
    return True, "compatible"
