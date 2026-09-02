from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import queue
import time
import traceback
from dataclasses import dataclass, fields
from types import SimpleNamespace
from typing import Any

import logfire
from grafico.deps import GraficoDeps

from domains.crest.crest_tools import run_crest_conformer_search
from domains.pyscf.tools.conversion_tools import UnitConvPair, get_conversion_factor
from domains.pyscf.tools.pyscf_workflow_tools import run_pyscf_workflow

from .config import Stage1Config


_STAGE1_CONFIG_FIELDS = {field.name for field in fields(Stage1Config)}


def _coerce_stage1_config(config: Stage1Config | dict[str, Any] | Any) -> Stage1Config:
    if isinstance(config, Stage1Config):
        return config.materialize()
    if hasattr(config, "to_jsonable_dict"):
        payload = config.to_jsonable_dict()
    elif isinstance(config, dict):
        payload = dict(config)
    else:
        payload = dict(vars(config))
    payload.pop("artifact_dir", None)
    filtered = {key: value for key, value in payload.items() if key in _STAGE1_CONFIG_FIELDS}
    return Stage1Config(**filtered).materialize()


@dataclass
class EvaluationResult:
    candidate_id: str
    parameter_values: dict[str, str]
    success: bool
    objective_values: dict[str, float] | None
    metadata: dict[str, Any]
    failure_reason: str | None = None
    suggestion_id: str | None = None

    def to_result_row(self) -> dict[str, Any]:
        if not self.success or not self.objective_values:
            raise ValueError("Cannot create BO result row from failed evaluation")
        conditions = {
            key: value
            for key, value in {
                "evaluation_stage": self.metadata.get("evaluation_stage"),
                "basis_set": ((self.metadata.get("pyscf") or {}).get("basis_set") if isinstance(self.metadata.get("pyscf"), dict) else None),
                "xc_functional": ((self.metadata.get("pyscf") or {}).get("xc_functional") if isinstance(self.metadata.get("pyscf"), dict) else None),
                "selected_state_energy_ev": ((self.metadata.get("objective_support") or {}).get("selected_state_energy_ev") if isinstance(self.metadata.get("objective_support"), dict) else self.metadata.get("synthetic_energy_ev")),
                "selected_state_oscillator_strength": ((self.metadata.get("objective_support") or {}).get("selected_state_oscillator_strength") if isinstance(self.metadata.get("objective_support"), dict) else None),
            }.items()
            if value is not None and isinstance(value, (str, int, float, bool))
        }
        notes_payload = {
            "candidate_id": self.candidate_id,
            "product_smiles": self.metadata.get("product_smiles"),
            "evaluation_backend": "synthetic" if self.metadata.get("synthetic_evaluator") else "digital",
        }
        return {
            "parameter_values": self.parameter_values,
            "objective_values": self.objective_values,
            "suggestion_id": self.suggestion_id,
            "metadata": {
                "experiment_id": self.candidate_id,
                "conditions": conditions or None,
                "notes": json.dumps(notes_payload, sort_keys=True),
            },
        }


def build_ctx() -> SimpleNamespace:
    return SimpleNamespace(
        deps=GraficoDeps(
            ws_url=os.getenv("GRAPHCHAT_AGENT_WS_URL") or os.getenv("VITE_WS_URL", "ws://graphchat:3000"),
            room=os.getenv("GRAPHCHAT_ROOM", "room"),
            sparql_endpoint=os.getenv("SPARQL_ENDPOINT", "http://blazegraph:8080/blazegraph/namespace/kb/sparql"),
        )
    )


def _normalise_floats(values: list[Any], limit: int) -> list[float]:
    cleaned: list[float] = []
    for value in values[:limit]:
        numeric = float(value)
        if math.isfinite(numeric):
            cleaned.append(numeric)
    return cleaned


def _ambiguity_penalty(crest_rows: list[dict[str, Any]], energy_window_kcal: float) -> tuple[float, dict[str, Any]]:
    if not crest_rows:
        raise ValueError("CREST returned no conformers")
    sorted_rows = sorted(crest_rows, key=lambda row: float(row["erel_kcal"]))
    accessible = [row for row in sorted_rows if float(row["erel_kcal"]) <= energy_window_kcal]
    total_weight = sum(max(float(row.get("weight_total", 0.0)), 0.0) for row in sorted_rows)
    if total_weight <= 0.0:
        weights = [1.0 / len(sorted_rows)] * len(sorted_rows)
    else:
        weights = [max(float(row.get("weight_total", 0.0)), 0.0) / total_weight for row in sorted_rows]
    dominant_weight = max(weights)
    entropy = -sum(weight * math.log(weight) for weight in weights if weight > 0.0)
    penalty = float((len(accessible) - 1) + (1.0 - dominant_weight) + entropy)
    metadata = {
        "crest_n_conformers": len(sorted_rows),
        "crest_accessible_conformers_within_window": len(accessible),
        "crest_energy_window_kcal": float(energy_window_kcal),
        "crest_dominant_weight": float(dominant_weight),
        "crest_weight_entropy": float(entropy),
    }
    return penalty, metadata


def _extract_excited_state_objectives(config: Stage1Config, pyscf_payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    tddft = pyscf_payload.get("tddft_results") or {}
    energies_h = _normalise_floats(tddft.get("tddft_singlet_energies") or [], config.low_state_window)
    oscillators = _normalise_floats(tddft.get("tddft_singlet_oscillator_strength") or [], config.low_state_window)
    n_pairs = min(len(energies_h), len(oscillators))
    if n_pairs == 0:
        raise ValueError("No finite low-lying singlet TDDFT states were available")
    energies_h = energies_h[:n_pairs]
    oscillators = oscillators[:n_pairs]
    brightest_index = max(range(n_pairs), key=lambda idx: oscillators[idx])
    conversion = get_conversion_factor(
        [UnitConvPair(value=float(value), from_unit="hartree", to_unit="eV") for value in energies_h]
    )
    if isinstance(conversion, str):
        raise ValueError(f"Unit conversion failed: {conversion}")
    energies_ev = [float(value) for value in conversion]
    bright_osc = float(oscillators[brightest_index])
    bright_energy_ev = float(energies_ev[brightest_index])
    if not math.isfinite(bright_osc) or not math.isfinite(bright_energy_ev):
        raise ValueError("Bright-state objective extraction produced non-finite values")
    objectives = {
        "bright_osc_strength": bright_osc,
        "color_error_ev": float(abs(bright_energy_ev - config.target_energy_ev)),
    }
    metadata = {
        "selected_state_index": int(brightest_index),
        "selected_state_energy_ev": bright_energy_ev,
        "selected_state_oscillator_strength": bright_osc,
        "low_state_window": int(config.low_state_window),
        "low_state_energies_ev": energies_ev,
        "low_state_oscillator_strengths": oscillators,
    }
    return objectives, metadata


def _evaluate_candidate_digital_inner(candidate: dict[str, Any], config: Stage1Config) -> EvaluationResult:
    ctx = build_ctx()
    logfire.info("Evaluating digital OSL candidate", candidate_id=candidate["candidate_id"])
    crest_rows = run_crest_conformer_search(
        ctx,
        identifier=candidate["product_smiles"],
        identifier_type="smiles",
        calculation_level_method=config.crest_method,
        threads=config.crest_threads,
    )
    if not isinstance(crest_rows, list) or not crest_rows:
        raise ValueError("CREST conformer search returned no conformer rows")
    ambiguity_penalty, crest_metadata = _ambiguity_penalty(crest_rows, config.ambiguity_window_kcal)
    lowest_conformer = min(crest_rows, key=lambda row: float(row["erel_kcal"]))
    conceptual_atoms_iri = lowest_conformer.get("conceptual_atoms_iri")
    if not conceptual_atoms_iri:
        raise ValueError("Lowest-energy conformer row did not contain conceptual_atoms_iri")

    pyscf_result = run_pyscf_workflow(
        ctx,
        summarised_user_query=(
            "Compute a cheap single-point DFT, low-lying TDDFT singlet excited states, and molecular analysis "
            "for the provided conformer. Skip geometry optimization and skip frequency analysis."
        ),
        identifier_type="conceptual_atoms_iri",
        identifier=conceptual_atoms_iri,
        basis_set=config.basis_set,
        xc_functional=config.xc_functional,
        tddft_nstates=config.tddft_nstates,
        workflow_timeout_s=config.pyscf_timeout_s,
        exit_node="MolecularAnalysis",
        update_graph=False,
    )
    payload = pyscf_result.model_dump(mode="json") if hasattr(pyscf_result, "model_dump") else pyscf_result
    excited_state_objectives, excited_state_metadata = _extract_excited_state_objectives(config, payload)
    objective_values = {
        **excited_state_objectives,
        "ambiguity_penalty": float(ambiguity_penalty),
    }
    if not all(math.isfinite(value) for value in objective_values.values()):
        raise ValueError(f"Non-finite objective values produced: {objective_values}")
    metadata = {
        "candidate_id": candidate["candidate_id"],
        "product_smiles": candidate["product_smiles"],
        "crest": {
            **crest_metadata,
            "lowest_erel_kcal": float(lowest_conformer["erel_kcal"]),
            "selected_conceptual_atoms_iri": conceptual_atoms_iri,
        },
        "pyscf": {
            "basis_set": config.basis_set,
            "xc_functional": config.xc_functional,
            "workflow_timeout_s": int(config.pyscf_timeout_s),
            "total_energy_hartree": float(payload.get("total_energy")),
            "workflow_summary": payload.get("workflow_summary"),
        },
        "objective_support": excited_state_metadata,
    }
    return EvaluationResult(
        candidate_id=candidate["candidate_id"],
        parameter_values={
            "cap_id": candidate["cap_id"],
            "bridge_id": candidate["bridge_id"],
            "core_id": candidate["core_id"],
        },
        success=True,
        objective_values=objective_values,
        metadata=metadata,
    )


def _evaluate_candidate_synthetic(candidate: dict[str, Any], config: Stage1Config) -> EvaluationResult:
    size_term = float(candidate["combined_heavy_atoms"])
    aromatic_term = float(candidate["combined_aromatic_rings"])
    rotatable_term = float(candidate["combined_rotatable_bonds"])
    hetero_term = float(candidate["combined_hetero_atoms"])
    bright_osc = max(0.01, 0.55 + 0.03 * aromatic_term - 0.008 * size_term - 0.02 * rotatable_term)
    synthetic_energy = 2.15 + 0.04 * aromatic_term + 0.015 * hetero_term - 0.01 * size_term
    ambiguity = max(0.0, 0.15 * rotatable_term + 0.08 * candidate["combined_fraction_csp3"])
    objective_values = {
        "bright_osc_strength": float(bright_osc),
        "color_error_ev": float(abs(synthetic_energy - config.target_energy_ev)),
        "ambiguity_penalty": float(ambiguity),
    }
    metadata = {
        "candidate_id": candidate["candidate_id"],
        "product_smiles": candidate["product_smiles"],
        "synthetic_evaluator": True,
        "synthetic_energy_ev": float(synthetic_energy),
    }
    return EvaluationResult(
        candidate_id=candidate["candidate_id"],
        parameter_values={
            "cap_id": candidate["cap_id"],
            "bridge_id": candidate["bridge_id"],
            "core_id": candidate["core_id"],
        },
        success=True,
        objective_values=objective_values,
        metadata=metadata,
    )


def _digital_worker(candidate: dict[str, Any], config_dict: dict[str, Any], result_queue: mp.Queue) -> None:
    try:
        config = _coerce_stage1_config(config_dict)
        result = _evaluate_candidate_digital_inner(candidate, config)
        result_queue.put({"ok": True, "payload": result.__dict__})
    except Exception as exc:  # noqa: BLE001
        result_queue.put(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=10),
            }
        )


def evaluate_candidate(candidate: dict[str, Any], config: Stage1Config | dict[str, Any] | Any, suggestion_id: str | None = None) -> EvaluationResult:
    config = _coerce_stage1_config(config)
    started = time.time()
    if config.evaluation_backend == "synthetic":
        result = _evaluate_candidate_synthetic(candidate, config)
        result.suggestion_id = suggestion_id
        result.metadata["wallclock_seconds"] = float(time.time() - started)
        return result

    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()
    worker_config = config.to_jsonable_dict()
    worker_config.pop("artifact_dir", None)
    worker = ctx.Process(target=_digital_worker, args=(candidate, worker_config, result_queue))
    worker.start()
    worker.join(config.evaluation_timeout_s)
    if worker.is_alive():
        worker.terminate()
        worker.join(30)
        return EvaluationResult(
            candidate_id=candidate["candidate_id"],
            parameter_values={
                "cap_id": candidate["cap_id"],
                "bridge_id": candidate["bridge_id"],
                "core_id": candidate["core_id"],
            },
            success=False,
            objective_values=None,
            metadata={"candidate_id": candidate["candidate_id"], "wallclock_seconds": float(time.time() - started)},
            failure_reason=(
                f"Candidate evaluation exceeded {config.evaluation_timeout_s} s wall-clock budget "
                f"(CREST + PySCF combined)"
            ),
            suggestion_id=suggestion_id,
        )
    try:
        message = result_queue.get_nowait()
    except queue.Empty:
        return EvaluationResult(
            candidate_id=candidate["candidate_id"],
            parameter_values={
                "cap_id": candidate["cap_id"],
                "bridge_id": candidate["bridge_id"],
                "core_id": candidate["core_id"],
            },
            success=False,
            objective_values=None,
            metadata={"candidate_id": candidate["candidate_id"], "wallclock_seconds": float(time.time() - started)},
            failure_reason=f"Evaluation worker exited without returning a result (exit_code={worker.exitcode})",
            suggestion_id=suggestion_id,
        )

    if not message.get("ok"):
        trace = message.get("traceback", "")
        trimmed_trace = trace.splitlines()[-8:]
        return EvaluationResult(
            candidate_id=candidate["candidate_id"],
            parameter_values={
                "cap_id": candidate["cap_id"],
                "bridge_id": candidate["bridge_id"],
                "core_id": candidate["core_id"],
            },
            success=False,
            objective_values=None,
            metadata={
                "candidate_id": candidate["candidate_id"],
                "traceback_tail": trimmed_trace,
                "wallclock_seconds": float(time.time() - started),
            },
            failure_reason=message.get("error", "Unknown evaluation worker failure"),
            suggestion_id=suggestion_id,
        )

    result = EvaluationResult(**message["payload"])
    result.suggestion_id = suggestion_id
    result.metadata["wallclock_seconds"] = float(time.time() - started)
    return result


def evaluate_candidates(candidates: list[dict[str, Any]], config: Stage1Config) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for candidate in candidates:
        results.append(evaluate_candidate(candidate, config, suggestion_id=candidate.get("suggestion_id")))
    return results


def result_to_jsonable(result: EvaluationResult) -> dict[str, Any]:
    return json.loads(json.dumps(result.__dict__, default=str))
