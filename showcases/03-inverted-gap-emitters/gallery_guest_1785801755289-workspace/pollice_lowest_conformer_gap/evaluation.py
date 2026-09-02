from __future__ import annotations

import contextlib
import hashlib
import math
import multiprocessing as mp
import os
import queue
import time
import traceback
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

from domains.crest.crest_tools import run_crest_conformer_search
from domains.pyscf.tools.pyscf_workflow_tools import run_pyscf_workflow
from grafico.deps import GraficoDeps

from .objective import as_dict, extract_gap
from .search_space import Candidate

RESULT_COLUMNS = [
    "molecule_key",
    "smiles_canonical",
    "n_conformers_generated",
    "selected_conformer_energy",
    "S1_ev",
    "T1_ev",
    "delta_est_ev",
    "objective",
    "oscillator_strength",
    "status",
    "crest_wall_s",
    "pyscf_wall_s",
    "total_eval_wall_s",
    "error_message",
]


def make_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        deps=GraficoDeps(
            ws_url=os.getenv("GRAPHCHAT_AGENT_WS_URL") or os.getenv("VITE_WS_URL", "ws://graphchat:3000"),
            room=os.getenv("GRAPHCHAT_ROOM", "room"),
            sparql_endpoint=os.getenv("SPARQL_ENDPOINT", "http://blazegraph:8080/blazegraph/namespace/kb/sparql"),
        )
    )


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_to_plain(v) for v in value]
    return value


def _flatten_dicts(value: Any) -> list[dict[str, Any]]:
    value = _to_plain(value)
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any("conceptual_atoms_iri" == str(k) for k in value):
            found.append(value)
        for item in value.values():
            found.extend(_flatten_dicts(item))
    elif isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            if any("conceptual_atoms_iri" in item for item in value):
                found.extend(value)
        for item in value:
            found.extend(_flatten_dicts(item))
    return found


def _first_number(row: dict[str, Any], tokens: tuple[str, ...]) -> float | None:
    for key, value in row.items():
        key_l = str(key).lower()
        if any(token in key_l for token in tokens):
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                return float(value)
    return None


def _select_lowest_conformer(crest_result: Any) -> tuple[str, int, float | None]:
    plain = _to_plain(crest_result)
    conformers = _flatten_dicts(plain)
    if not conformers and isinstance(plain, dict) and plain.get("conceptual_atoms_iri"):
        conformers = [plain]
    if not conformers:
        raise ValueError("CREST result did not expose any conformer conceptual_atoms_iri.")

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for i, conformer in enumerate(conformers):
        energy = _first_number(conformer, ("energy",))
        ranked.append((float("inf") if energy is None else energy, i, conformer))
    energy, _i, selected = min(ranked, key=lambda item: (item[0], item[1]))
    iri = selected.get("conceptual_atoms_iri")
    if not iri:
        raise ValueError("Selected CREST conformer has no conceptual_atoms_iri.")
    return str(iri), len(conformers), (None if math.isinf(energy) else float(energy))


def synthetic_evaluation(candidate: Candidate) -> dict[str, Any]:
    seed = int(hashlib.sha256(candidate.molecule_key.encode()).hexdigest()[:8], 16)
    s1 = 1.8 + (seed % 1200) / 1000.0
    t1 = s1 - (0.05 + ((seed // 1200) % 800) / 1000.0)
    gap = s1 - t1
    return {
        "molecule_key": candidate.molecule_key,
        "smiles_canonical": candidate.smiles_canonical,
        "n_conformers_generated": 1,
        "selected_conformer_energy": None,
        "S1_ev": s1,
        "T1_ev": t1,
        "delta_est_ev": gap,
        "objective": -gap,
        "oscillator_strength": ((seed // 37) % 1000) / 100000.0,
        "status": "success",
        "crest_wall_s": 0.0,
        "pyscf_wall_s": 0.0,
        "total_eval_wall_s": 0.0,
        "error_message": "synthetic smoke-test evaluator; not a chemistry result",
    }


def _worker(
    candidate_data: dict[str, Any],
    queue_out: mp.Queue,
    pyscf_timeout_s: float | None,
    crest_threads: int,
    child_log_path: str | None,
) -> None:
    candidate = Candidate(**candidate_data)
    total_start = time.monotonic()
    base = {
        "molecule_key": candidate.molecule_key,
        "smiles_canonical": candidate.smiles_canonical,
        "n_conformers_generated": None,
        "selected_conformer_energy": None,
        "S1_ev": None,
        "T1_ev": None,
        "delta_est_ev": None,
        "objective": None,
        "oscillator_strength": None,
        "status": "failed",
        "crest_wall_s": None,
        "pyscf_wall_s": None,
        "total_eval_wall_s": None,
        "error_message": "",
    }
    log_handle = open(child_log_path, "a", encoding="utf-8") if child_log_path else open(os.devnull, "w", encoding="utf-8")
    try:
        with log_handle, contextlib.redirect_stdout(log_handle), contextlib.redirect_stderr(log_handle):
            ctx = make_ctx()
            crest_start = time.monotonic()
            crest_result = run_crest_conformer_search(
                ctx,
                identifier=candidate.smiles_canonical,
                identifier_type="smiles",
                charge=0,
                spin_multiplicity=1,
                implicit_solvent=None,
                calculation_level_method="gfn2",
                crest_runtype="imtd-gc",
                run_on_gpu=False,
                threads=crest_threads,
            )
            base["crest_wall_s"] = time.monotonic() - crest_start
            iri, n_conformers, selected_energy = _select_lowest_conformer(crest_result)
            base["n_conformers_generated"] = n_conformers
            base["selected_conformer_energy"] = selected_energy

            pyscf_start = time.monotonic()
            pyscf_result = run_pyscf_workflow(
                ctx,
                summarised_user_query=(
                    "Run restricted closed-shell PBE0/def2-SVP gas-phase TD-DFT single-point "
                    "on this fixed CREST conformer; do not change charge or spin; extract low-lying "
                    "singlet and triplet excitation energies and oscillator strengths."
                ),
                identifier_type="conceptual_atoms_iri",
                identifier=iri,
                charge=0,
                spin_multiplicity=1,
                basis_set="def2-svp",
                restricted=True,
                xc_functional="PBE0",
                solvation_model=None,
                implicit_solvent=None,
                update_graph=False,
                tddft_nstates=5,
                workflow_timeout_s=pyscf_timeout_s,
            )
            base["pyscf_wall_s"] = time.monotonic() - pyscf_start
            base.update(extract_gap(pyscf_result))
            base["status"] = "success"
    except Exception as exc:
        base["error_message"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=6)}"[:3000]
    finally:
        base["total_eval_wall_s"] = time.monotonic() - total_start
        queue_out.put(base)


def evaluate_candidate(
    candidate: Candidate,
    *,
    synthetic: bool = False,
    eval_timeout_s: float = 7200.0,
    pyscf_timeout_s: float | None = 5400.0,
    crest_threads: int = 4,
    child_log_path: str | None = None,
) -> dict[str, Any]:
    if synthetic:
        return synthetic_evaluation(candidate)

    ctx = mp.get_context("spawn")
    queue_out: mp.Queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_worker, args=(asdict(candidate), queue_out, pyscf_timeout_s, crest_threads, child_log_path))
    proc.start()
    proc.join(eval_timeout_s)
    if proc.is_alive():
        proc.terminate()
        proc.join(30)
        if proc.is_alive():
            proc.kill()
            proc.join()
        return {
            "molecule_key": candidate.molecule_key,
            "smiles_canonical": candidate.smiles_canonical,
            "n_conformers_generated": None,
            "selected_conformer_energy": None,
            "S1_ev": None,
            "T1_ev": None,
            "delta_est_ev": None,
            "objective": None,
            "oscillator_strength": None,
            "status": "failed",
            "crest_wall_s": None,
            "pyscf_wall_s": None,
            "total_eval_wall_s": eval_timeout_s,
            "error_message": f"Evaluation timed out after {eval_timeout_s} s",
        }
    try:
        return queue_out.get_nowait()
    except queue.Empty:
        return {
            "molecule_key": candidate.molecule_key,
            "smiles_canonical": candidate.smiles_canonical,
            "n_conformers_generated": None,
            "selected_conformer_energy": None,
            "S1_ev": None,
            "T1_ev": None,
            "delta_est_ev": None,
            "objective": None,
            "oscillator_strength": None,
            "status": "failed",
            "crest_wall_s": None,
            "pyscf_wall_s": None,
            "total_eval_wall_s": None,
            "error_message": f"Evaluation process exited with code {proc.exitcode} and returned no result",
        }


def run_pyscf_smoke(timeout_s: float = 120.0, log_path: str | None = None) -> dict[str, Any]:
    ctx = make_ctx()
    start = time.monotonic()
    log_handle = open(log_path, "a", encoding="utf-8") if log_path else open(os.devnull, "w", encoding="utf-8")
    with log_handle, contextlib.redirect_stdout(log_handle), contextlib.redirect_stderr(log_handle):
        result = run_pyscf_workflow(
            ctx,
            summarised_user_query="Run a tiny restricted PBE0/STO-3G TD-DFT smoke test and return excited-state data.",
            identifier_type="smiles",
            identifier="O",
            charge=0,
            spin_multiplicity=1,
            basis_set="sto-3g",
            restricted=True,
            xc_functional="PBE0",
            solvation_model=None,
            implicit_solvent=None,
            update_graph=False,
            tddft_nstates=1,
            workflow_timeout_s=timeout_s,
        )
    out = extract_gap(result)
    out["wall_s"] = time.monotonic() - start
    return out
