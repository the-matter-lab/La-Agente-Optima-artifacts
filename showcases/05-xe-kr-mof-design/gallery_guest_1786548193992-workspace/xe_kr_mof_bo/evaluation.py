from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import warnings
from pathlib import Path

from domains.mofs.ontomofs import BuildingBlock, MOFBuilder, Topology

from .search_space import is_compatible


def _quiet_pormake() -> None:
    try:
        import pormake.log as pormake_log

        pormake_log.console_log_handler.setLevel(logging.CRITICAL)
    except Exception:
        pass


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return value


def _score(pld: float, lcd: float, pv_cm3_g: float) -> dict[str, float]:
    # Xe kinetic diameter is ~4.1 Å and Kr is ~3.6 Å; this example proxy rewards
    # sub-nanometer PLD/LCD windows while retaining a separate pore-volume objective.
    if pld < 3.6:
        pld_score = math.exp(-((3.6 - pld) / 0.6) ** 2)
    elif pld <= 7.0:
        pld_score = 1.0
    else:
        pld_score = math.exp(-((pld - 7.0) / 5.0) ** 2)
    lcd_score = 1.0 / (1.0 + max(0.0, lcd - 12.0) / 12.0)
    return {
        "selectivity_proxy": max(0.0, min(1.0, pld_score * lcd_score)),
        "capacity_proxy": max(0.0, float(pv_cm3_g)),
    }


def evaluate_candidate(params: dict, *, space: dict, artifact_dir: Path) -> dict:
    topology = str(params["topology"])
    node = str(params["node"])
    edge = str(params["edge"])
    name = f"{topology}_{node}_{edge}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ok, reason = is_compatible(space, topology, node, edge)
    if not ok:
        return {
            "ok": False,
            "name": name,
            "parameters": params,
            "objectives": {"selectivity_proxy": 0.0, "capacity_proxy": 0.0},
            "notes": f"penalized incompatible candidate: {reason}",
        }

    captured = io.StringIO()
    try:
        _quiet_pormake()
        with warnings.catch_warnings(), contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            warnings.simplefilter("ignore")
            topo = Topology.from_pormake_db_id(topology)
            node_bb = BuildingBlock.from_pormake_db_id(node)
            edge_bb = BuildingBlock.from_pormake_db_id(edge)
            node_map = {int(nt): node_bb for nt in topo.pm_topology.unique_node_types}
            edge_map = {tuple(map(int, et)): edge_bb for et in topo.pm_topology.unique_edge_types}
            mof = MOFBuilder().build_by_type(topo, node_bbs=node_map, edge_bbs=edge_map, name=name)
            pd = mof.run_zeopp_pore_diameter()
            pv = mof.run_zeopp_pore_volume()
        pd_data = _jsonable(pd)
        pv_data = _jsonable(pv)
        if "error_message" in pd_data or "error_message" in pv_data:
            raise RuntimeError(f"Zeo++ error: {pd_data.get('error_message') or pv_data.get('error_message')}")
        pld = float(pd_data["PLD"])
        lcd = float(pd_data["LCD"])
        lfpd = float(pd_data.get("LFPD", 0.0))
        pv_cm3_g = float(pv_data["pv_cm3_g"])
        objectives = _score(pld, lcd, pv_cm3_g)
        record = {
            "ok": True,
            "name": name,
            "parameters": params,
            "objectives": objectives,
            "metrics": {"PLD_A": pld, "LCD_A": lcd, "LFPD_A": lfpd, "pore_volume_cm3_g": pv_cm3_g},
            "notes": "constructed with PORMAKE; analyzed by Zeo++ pore diameter and pore volume",
        }
        cif_path = artifact_dir / f"{name}.cif"
        if getattr(mof, "cif_text", None):
            cif_path.write_text(mof.cif_text)
            record["cif_path"] = str(cif_path)
        return record
    except Exception as exc:
        return {
            "ok": False,
            "name": name,
            "parameters": params,
            "objectives": {"selectivity_proxy": 0.0, "capacity_proxy": 0.0},
            "notes": f"penalized evaluation failure: {type(exc).__name__}: {exc}",
            "captured_output": captured.getvalue()[-4000:],
        }


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_jsonable(record), sort_keys=True) + "\n")
