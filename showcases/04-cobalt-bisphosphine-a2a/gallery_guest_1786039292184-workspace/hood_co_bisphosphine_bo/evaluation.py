from __future__ import annotations

import asyncio
import contextlib
import io
import json
import math
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import logfire
from domains.estructural_a2a.client import EstructuralClient
from domains.pyscf.tools.pyscf_workflow_tools import run_pyscf_workflow
from grafico.deps import GraficoDeps

from .descriptors import HARTREE_TO_EV, electronic_activation_components, extract_electronic_values, geometry_descriptors, objective_scores, parse_xyz
from .library import Candidate, SUBSTITUENT_FULL_NAMES



class InfrastructureEvaluationError(RuntimeError):
    """Evaluation failed before chemistry because infrastructure was unavailable."""


def _is_infrastructure_error(exc: Exception) -> bool:
    text = str(exc).lower()
    needles = (
        "temporary failure in name resolution",
        "name resolution",
        "connection refused",
        "connection reset",
        "connection timed out",
        "nodename nor servname",
        "failed to establish a new connection",
        "network is unreachable",
        "did not create expected xyz file",
        "xyz file not found",
        "filenotfounderror",
        "estructural workspace preflight failed",
    )
    return any(needle in text for needle in needles)



def estructural_context_id() -> str:
    return os.getenv("GRAPHCHAT_ROOM") or Path.cwd().name
def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        deps=GraficoDeps(
            ws_url=os.getenv("GRAPHCHAT_AGENT_WS_URL") or os.getenv("VITE_WS_URL", "ws://graphchat:3000"),
            room=estructural_context_id(),
            sparql_endpoint=os.getenv("SPARQL_ENDPOINT", "http://blazegraph:8080/blazegraph/namespace/kb/sparql"),
        )
    )


def _jsonable(obj):
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except TypeError:
            return obj.model_dump()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in obj]
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return str(obj)


def _atoms_from_pyscf_result(result_dump) -> list[tuple[str, float, float, float]]:
    if not isinstance(result_dump, dict):
        return []
    xyz = (result_dump.get("final_molecule") or {}).get("xyz") or {}
    numbers = xyz.get("atomic_numbers") or []
    positions = xyz.get("positions") or []
    symbol_by_z = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F", 15: "P", 17: "Cl", 27: "Co"}
    atoms = []
    for z, pos in zip(numbers, positions):
        if len(pos) >= 3:
            atoms.append((symbol_by_z.get(int(z), str(z)), float(pos[0]), float(pos[1]), float(pos[2])))
    return atoms


def _generated_xyz_from_text(text: str, expected: Path, fallback_name: str | None = None) -> Path:
    if expected.exists():
        return expected
    candidates = []
    if fallback_name:
        candidates.append(Path(fallback_name))
    candidates.append(Path(expected.name))
    for match in re.findall(r"[\w./-]+\.xyz", text):
        candidates.append(Path(match))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Estructural did not create expected XYZ file {expected}")


def run_estructural_workspace_preflight(artifacts_dir: Path) -> Path:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    filename = f"estructural_preflight_{os.getpid()}.xyz"
    path = Path(filename)
    if path.exists():
        path.unlink()
    client = EstructuralClient.from_env()
    result = asyncio.run(
        client.send(
            f"Generate a simple valid 3D XYZ structure for water and save it exactly as {filename} in the current workspace. Return only the filename.",
            context_id=estructural_context_id(),
        )
    )
    (artifacts_dir / "estructural_preflight_response.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    if not path.exists():
        raise InfrastructureEvaluationError(
            f"Estructural workspace preflight failed: endpoint responded but did not create {filename} in context {estructural_context_id()}"
        )
    atoms = parse_xyz(path.as_posix())
    if len(atoms) < 3:
        raise InfrastructureEvaluationError(f"Estructural workspace preflight failed: {filename} is not a parseable water XYZ")
    final_path = artifacts_dir / filename
    shutil.move(path.as_posix(), final_path.as_posix())
    return final_path


def build_complex_with_estructural(candidate: Candidate, artifacts_dir: Path) -> Path:
    candidate_dir = artifacts_dir / candidate.candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    xyz_path = candidate_dir / f"{candidate.candidate_id}.xyz"
    workspace_xyz_name = f"estructural_{candidate.candidate_id}.xyz"
    prompt = f"""
Generate a chemically plausible 3D XYZ structure for the cationic Co(II) precursor-like complex [Co(acac)(P2)]+.
P2 is the bidentate bisphosphine ligand {candidate.ligand_label}: {candidate.ligand_description}.
Use acac = acetylacetonate bound O,O to Co. Ensure both phosphorus donors bind to Co, acac remains O,O-bound, and the structure is suitable as an initial geometry for modest DFT optimization.
Substituent definitions: p-Tol is 4-methylphenyl; p-Anisyl is 4-methoxyphenyl; p-CF3-Ph is 4-trifluoromethylphenyl.
Write only an XYZ structure file named exactly {workspace_xyz_name} in the current workspace root, not inside a subdirectory.
Do not run quantum calculations.
""".strip()
    client = EstructuralClient.from_env()
    result = asyncio.run(client.send(prompt, context_id=estructural_context_id()))
    (candidate_dir / "estructural_response.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    (candidate_dir / "estructural_response.txt").write_text(result.get("text", ""), encoding="utf-8")
    logfire.info("estructural_completed", candidate_id=candidate.candidate_id, task_id=result.get("task_id"))
    produced = _generated_xyz_from_text(result.get("text", ""), xyz_path, fallback_name=workspace_xyz_name)
    if produced.resolve() != xyz_path.resolve():
        shutil.move(produced.as_posix(), xyz_path.as_posix())
    return xyz_path


def run_geometry_optimization(
    xyz_path: Path,
    *,
    charge: int,
    spin_multiplicity: int,
    basis_set: str,
    xc_functional: str,
    geometry_max_steps: int,
    workflow_timeout_s: float | None,
) -> tuple[dict, str]:
    query = (
        f"Run unrestricted {xc_functional}/{basis_set} DFT geometry optimization for this cationic Co(II) "
        "bisphosphine acac complex and continue until the geometry optimization has actually "
        "converged within the allowed step limit. After the converged geometry optimization, run "
        "molecular/electronic analysis and return Mulliken/Lowdin/IAO charges, spin populations, "
        "orbital energies, occupations, and the PySCF chkfile. Do not run frequencies, TDDFT, "
        "transition states, catalytic-cycle calculations, or energy-span calculations."
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    xyz_text = xyz_path.read_text(encoding="utf-8")
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = run_pyscf_workflow(
            _ctx(),
            summarised_user_query=query,
            identifier_type="xyz",
            identifier=xyz_text,
            charge=charge,
            spin_multiplicity=spin_multiplicity,
            basis_set=basis_set,
            restricted=False,
            xc_functional=xc_functional,
            geometry_max_steps=geometry_max_steps,
            update_graph=False,
            workflow_timeout_s=workflow_timeout_s,
        )
    captured = stdout.getvalue() + stderr.getvalue()
    return _jsonable(result), captured



def run_pyscf_literal_xyz_preflight(xyz_path: Path, artifacts_dir: Path, timeout_s: float = 120.0) -> None:
    xyz_text = xyz_path.read_text(encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = run_pyscf_workflow(
            _ctx(),
            summarised_user_query="Run a tiny DFT geometry optimisation only for XYZ literal handoff preflight; no frequencies and no TDDFT.",
            identifier_type="xyz",
            identifier=xyz_text,
            charge=0,
            spin_multiplicity=1,
            basis_set="sto-3g",
            restricted=True,
            xc_functional="pbe",
            geometry_max_steps=1,
            update_graph=False,
            workflow_timeout_s=timeout_s,
        )
    result_dump = _jsonable(result)
    (artifacts_dir / "pyscf_literal_preflight_result.json").write_text(json.dumps(result_dump, indent=2), encoding="utf-8")
    captured = stdout.getvalue() + stderr.getvalue()
    if captured.strip():
        (artifacts_dir / "pyscf_literal_preflight_console.txt").write_text(captured, encoding="utf-8")
    if not (isinstance(result_dump, dict) and result_dump.get("total_energy") is not None):
        raise InfrastructureEvaluationError("PySCF literal XYZ preflight failed: no total_energy returned")



def _frontier_from_energies(energies, occs) -> dict:
    vals = energies.tolist() if hasattr(energies, "tolist") else list(energies or [])
    occ_vals = occs.tolist() if hasattr(occs, "tolist") else list(occs or [])
    occupied = [i for i, occ in enumerate(occ_vals) if float(occ) > 0.1]
    if not occupied:
        return {}
    homo_i = max(occupied)
    lumo_i = next((i for i in range(homo_i + 1, len(vals)) if i < len(occ_vals) and float(occ_vals[i]) < 0.1), homo_i + 1 if homo_i + 1 < len(vals) else None)
    out = {"homo_index": homo_i, "homo_hartree": float(vals[homo_i]), "homo_eV": float(vals[homo_i]) * HARTREE_TO_EV}
    if lumo_i is not None:
        out.update({"lumo_index": lumo_i, "lumo_hartree": float(vals[lumo_i]), "lumo_eV": float(vals[lumo_i]) * HARTREE_TO_EV})
    return out


def parse_electronic_descriptors(result_dump: dict) -> dict:
    fallback = extract_electronic_values(result_dump)
    chkfile = ((result_dump.get("pyscf_output") or {}).get("chkfile") if isinstance(result_dump, dict) else None)
    if not chkfile:
        return fallback
    try:
        from pyscf.scf import chkfile as pyscf_chkfile
        from pyscf.scf import uhf

        mol, scf_rec = pyscf_chkfile.load_scf(chkfile)
        mo_energy = scf_rec["mo_energy"]
        mo_occ = scf_rec["mo_occ"]
        mo_coeff = scf_rec["mo_coeff"]
        unrestricted = getattr(mo_energy, "ndim", 1) == 2
        co_index = next((i for i in range(mol.natm) if mol.atom_symbol(i).lower() == "co"), 0)
        out = {
            **fallback,
            "provenance": "chkfile_preferred",
            "chkfile": chkfile,
            "co_atom_index": co_index,
            "co_symbol": mol.atom_symbol(co_index),
            "nelectrons": int(mol.nelectron),
            "spin": int(mol.spin),
            "unrestricted": bool(unrestricted),
        }
        if unrestricted:
            alpha = _frontier_from_energies(mo_energy[0], mo_occ[0])
            beta = _frontier_from_energies(mo_energy[1], mo_occ[1])
            nalpha = int(sum(1 for occ in mo_occ[0].tolist() if float(occ) > 0.1))
            nbeta = int(sum(1 for occ in mo_occ[1].tolist() if float(occ) > 0.1))
            out.update({"nalpha": nalpha, "nbeta": nbeta, "alpha_frontier": alpha, "beta_frontier": beta})
            somo = alpha if nalpha > nbeta else (beta if nbeta > nalpha else alpha)
            if somo:
                out["somo_energy_hartree"] = somo.get("homo_hartree")
                out["somo_energy_eV"] = somo.get("homo_eV")
                out["somo_spin_channel"] = "alpha" if somo is alpha else "beta"
            homos = [x for x in (alpha.get("homo_hartree"), beta.get("homo_hartree")) if x is not None]
            if homos:
                out["homo_energy_hartree"] = max(homos)
                out["homo_energy_eV"] = out["homo_energy_hartree"] * HARTREE_TO_EV
            dm = uhf.make_rdm1(mo_coeff, mo_occ)
            s = mol.intor_symmetric("int1e_ovlp")
            pop, charges = uhf.mulliken_pop(mol, dm, s=s, verbose=0)
            ao0, ao1 = mol.aoslice_by_atom()[co_index][2:4]
            alpha_e = float(pop[0][ao0:ao1].sum())
            beta_e = float(pop[1][ao0:ao1].sum())
            out.update(
                {
                    "co_mulliken_alpha_electrons": alpha_e,
                    "co_mulliken_beta_electrons": beta_e,
                    "co_mulliken_total_electrons": alpha_e + beta_e,
                    "co_mulliken_spin_population": alpha_e - beta_e,
                    "co_mulliken_charge": float(charges[co_index]),
                }
            )
        else:
            frontier = _frontier_from_energies(mo_energy, mo_occ)
            out.update({"frontier": frontier})
            if frontier:
                out["homo_energy_hartree"] = frontier.get("homo_hartree")
                out["homo_energy_eV"] = frontier.get("homo_eV")
                out["somo_energy_hartree"] = frontier.get("homo_hartree")
                out["somo_energy_eV"] = frontier.get("homo_eV")
        return out
    except Exception as exc:
        fallback["provenance"] = "analysis_results_fallback_after_chkfile_error"
        fallback["chkfile"] = chkfile
        fallback["chkfile_parse_error"] = str(exc)
        return fallback
def _validity_from_result(result_dump: dict) -> dict:
    total_energy = result_dump.get("total_energy") if isinstance(result_dump, dict) else None
    if total_energy is None and isinstance(result_dump, list) and result_dump:
        total_energy = result_dump[0].get("energy") if isinstance(result_dump[0], dict) else None
    summary = result_dump.get("workflow_summary") if isinstance(result_dump, dict) else []
    if not isinstance(summary, list):
        summary = [str(summary)] if summary else []
    summary_text = "\n".join(str(x) for x in summary).lower()
    full_text = json.dumps(result_dump).lower()
    geometry_completed = "geometry optimization completed" in summary_text or "geometry optimisation completed" in summary_text
    molecular_analysis_completed = "molecular analysis completed" in summary_text
    failure_terms = (
        "error in geometry optimization",
        "error in geometry optimisation",
        "nuclear gradients",
        "not converged",
        "timeout",
        "timed out",
        "failed",
        "exception",
    )
    optimization_failed = any(term in summary_text for term in failure_terms)
    scf_failed = any(term in full_text for term in ('"converged": false', "converged': false", "scf failed", "scf did not converge"))
    return {
        "scf_converged": bool(total_energy is not None and not scf_failed),
        "optimization_success": bool(geometry_completed and not optimization_failed),
        "molecular_analysis_success": bool(molecular_analysis_completed),
        "geometry_completed_summary": geometry_completed,
        "optimization_failure_terms_present": optimization_failed,
        "total_energy": total_energy,
    }


def mock_evaluate(candidate: Candidate, artifacts_dir: Path) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    steric_map = {"Me": 0.0, "Et": 0.3, "iPr": 0.6, "Cy": 0.9, "Ph": 0.7, "p-Tol": 0.8, "p-Anisyl": 0.85, "p-CF3-Ph": 1.0}
    elec_map = {"Me": 0.0, "Et": 0.05, "iPr": 0.08, "Cy": 0.04, "Ph": -0.05, "p-Tol": -0.02, "p-Anisyl": -0.12, "p-CF3-Ph": 0.18}
    linker_geom = {"ethylene": 8.0, "propylene": 6.5, "1,2-phenylene": 7.0, "cis-1,2-cyclohexylene": 7.5}
    crowd = steric_map[candidate.r1] + steric_map[candidate.r2]
    asym = abs(steric_map[candidate.r1] - steric_map[candidate.r2])
    objectives = {
        "electronic_activation": 1.0 + elec_map[candidate.r1] + elec_map[candidate.r2] - 0.1 * crowd,
        "coordination_stability": 8.0 - 2.0 * asym - 0.3 * crowd,
        "chelate_geometry": linker_geom[candidate.linker] - asym,
        "steric_crowding": crowd,
    }
    record = {
        "candidate": candidate.asdict(),
        "mode": "mock",
        "validity": {"scf_converged": True, "optimization_success": True},
        "descriptors": {"mock_note": "deterministic smoke-test surrogate; no chemistry calculations run"},
        "objectives": objectives,
        "feasible": True,
    }
    (artifacts_dir / f"{candidate.candidate_id}_mock_result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def evaluate_candidate(
    candidate: Candidate,
    artifacts_dir: Path,
    *,
    mock: bool,
    charge: int,
    spin_multiplicity: int,
    basis_set: str,
    xc_functional: str,
    geometry_max_steps: int,
    workflow_timeout_s: float | None,
) -> dict:
    if mock:
        return mock_evaluate(candidate, artifacts_dir)
    candidate_dir = artifacts_dir / candidate.candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    try:
        xyz_path = build_complex_with_estructural(candidate, artifacts_dir)
        result_dump, captured = run_geometry_optimization(
            xyz_path,
            charge=charge,
            spin_multiplicity=spin_multiplicity,
            basis_set=basis_set,
            xc_functional=xc_functional,
            geometry_max_steps=geometry_max_steps,
            workflow_timeout_s=workflow_timeout_s,
        )
        if captured.strip():
            (candidate_dir / "pyscf_console.txt").write_text(captured, encoding="utf-8")
        atoms = _atoms_from_pyscf_result(result_dump) or parse_xyz(xyz_path.as_posix())
        geom = geometry_descriptors(atoms)
        electronic = parse_electronic_descriptors(result_dump if isinstance(result_dump, dict) else {"result": result_dump})
        validity = _validity_from_result(result_dump)
        objectives = objective_scores(validity, geom, electronic)
        objective_components = {"electronic_activation": electronic_activation_components(electronic)}
        feasible = all(v > -99.0 for k, v in objectives.items() if k != "steric_crowding") and objectives["steric_crowding"] < 99.0
        record = {
            "candidate": candidate.asdict(),
            "mode": "pyscf",
            "assumptions": {
                "complex_charge": charge,
                "spin_multiplicity": spin_multiplicity,
                "basis_set": basis_set,
                "xc_functional": xc_functional,
                "geometry_max_steps": geometry_max_steps,
                "requires_geometry_optimization_summary_completed": True,
            },
            "xyz_path": xyz_path.as_posix(),
            "validity": validity,
            "geometry_descriptors": geom,
            "electronic_descriptors": electronic,
            "objectives": objectives,
            "objective_components": objective_components,
            "feasible": feasible,
            "pyscf_result": result_dump,
        }
    except Exception as exc:
        logfire.info("candidate_evaluation_failed", candidate_id=candidate.candidate_id, error=str(exc))
        if _is_infrastructure_error(exc):
            record = {
                "candidate": candidate.asdict(),
                "mode": "infrastructure_failed",
                "validity": {"scf_converged": False, "optimization_success": False, "error": str(exc)},
                "feasible": False,
            }
            (candidate_dir / "infrastructure_failure.json").write_text(json.dumps(_jsonable(record), indent=2), encoding="utf-8")
            raise InfrastructureEvaluationError(str(exc)) from exc
        record = {
            "candidate": candidate.asdict(),
            "mode": "failed",
            "validity": {"scf_converged": False, "optimization_success": False, "error": str(exc)},
            "objectives": {
                "electronic_activation": -100.0,
                "coordination_stability": -100.0,
                "chelate_geometry": -100.0,
                "steric_crowding": 100.0,
            },
            "feasible": False,
        }
    (candidate_dir / "evaluation.json").write_text(json.dumps(_jsonable(record), indent=2), encoding="utf-8")
    return record
