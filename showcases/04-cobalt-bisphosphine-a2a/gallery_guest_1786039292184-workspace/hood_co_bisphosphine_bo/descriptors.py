from __future__ import annotations

import math
from itertools import combinations
from typing import Any

Atom = tuple[str, float, float, float]
HARTREE_TO_EV = 27.211386245988


def parse_xyz(path: str) -> list[Atom]:
    with open(path, "r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    try:
        natoms = int(lines[0].split()[0])
        atom_lines = lines[2 : 2 + natoms]
    except Exception:
        atom_lines = lines
    atoms: list[Atom] = []
    for line in atom_lines:
        parts = line.split()
        if len(parts) >= 4:
            try:
                atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                pass
    return atoms


def _dist(a: Atom, b: Atom) -> float:
    return math.sqrt((a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 + (a[3] - b[3]) ** 2)


def _vec(a: Atom, b: Atom) -> tuple[float, float, float]:
    return (a[1] - b[1], a[2] - b[2], a[3] - b[3])


def _dot(u: tuple[float, float, float], v: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(u, v))


def _norm(u: tuple[float, float, float]) -> float:
    return math.sqrt(max(_dot(u, u), 0.0))


def _angle(a: Atom, center: Atom, b: Atom) -> float | None:
    u, v = _vec(a, center), _vec(b, center)
    den = _norm(u) * _norm(v)
    if den == 0:
        return None
    c = max(-1.0, min(1.0, _dot(u, v) / den))
    return math.degrees(math.acos(c))


def _find_atoms(atoms: list[Atom], symbol: str) -> list[Atom]:
    return [a for a in atoms if a[0].lower() == symbol.lower()]


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _listify(value: Any) -> list:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def extract_electronic_values(result_dump: dict) -> dict[str, Any]:
    """Fallback extraction from PySCF workflow analysis arrays.

    The production evaluator prefers chkfile parsing. This function keeps a
    conservative analysis_results fallback for environments where the chkfile is
    unavailable. Energies are in Hartree unless a key explicitly says otherwise.
    """
    found: dict[str, Any] = {
        "somo_energy_hartree": None,
        "homo_energy_hartree": None,
        "somo_energy_eV": None,
        "homo_energy_eV": None,
        "co_mulliken_charge": None,
        "co_lowdin_charge": None,
        "co_iao_charge": None,
        "co_mulliken_spin_population": None,
        "provenance": "analysis_results_fallback",
    }
    if not isinstance(result_dump, dict):
        return found
    analysis = result_dump.get("analysis_results") or {}
    if hasattr(analysis, "model_dump"):
        analysis = analysis.model_dump()
    if not isinstance(analysis, dict):
        analysis = {}

    atomic_numbers = _listify(((result_dump.get("final_molecule") or {}).get("xyz") or {}).get("atomic_numbers"))
    co_index = next((i for i, z in enumerate(atomic_numbers) if int(z) == 27), 0 if atomic_numbers else None)
    for key, target in (
        ("atomic_charges_mulliken", "co_mulliken_charge"),
        ("atomic_charges_lowdin", "co_lowdin_charge"),
        ("atomic_charges_iao", "co_iao_charge"),
    ):
        vals = _listify(analysis.get(key))
        if co_index is not None and len(vals) > co_index:
            found[target] = _safe_float(vals[co_index])
    for key in ("spin_populations_mulliken", "mulliken_spin_populations", "atomic_spin_populations"):
        vals = _listify(analysis.get(key))
        if co_index is not None and len(vals) > co_index:
            found["co_mulliken_spin_population"] = _safe_float(vals[co_index])
            break

    alpha = _listify(analysis.get("orbital_energies"))
    beta = _listify(analysis.get("orbital_energies_beta"))
    occ_alpha = _listify(analysis.get("orbital_occupations"))
    occ_beta = _listify(analysis.get("orbital_occupations_beta"))
    if alpha and occ_alpha:
        occ_idx = [i for i, occ in enumerate(occ_alpha) if _safe_float(occ) and _safe_float(occ) > 0.1]
        if occ_idx:
            found["homo_energy_hartree"] = _safe_float(alpha[max(occ_idx)])
    if beta and occ_beta:
        occ_idx_b = [i for i, occ in enumerate(occ_beta) if _safe_float(occ) and _safe_float(occ) > 0.1]
        if occ_idx_b:
            beta_homo = _safe_float(beta[max(occ_idx_b)])
            if found["homo_energy_hartree"] is None or (beta_homo is not None and beta_homo > found["homo_energy_hartree"]):
                found["homo_energy_hartree"] = beta_homo
    found["somo_energy_hartree"] = found["homo_energy_hartree"]
    if found["homo_energy_hartree"] is not None:
        found["homo_energy_eV"] = found["homo_energy_hartree"] * HARTREE_TO_EV
    if found["somo_energy_hartree"] is not None:
        found["somo_energy_eV"] = found["somo_energy_hartree"] * HARTREE_TO_EV
    return found


def electronic_activation_components(electronic: dict[str, Any]) -> dict[str, Any]:
    somo = _safe_float(electronic.get("somo_energy_hartree") or electronic.get("somo_energy") or electronic.get("homo_energy_hartree") or electronic.get("homo_energy"))
    charge = _safe_float(electronic.get("co_mulliken_charge") if electronic.get("co_mulliken_charge") is not None else electronic.get("co_charge"))
    spin = _safe_float(electronic.get("co_mulliken_spin_population") if electronic.get("co_mulliken_spin_population") is not None else electronic.get("co_spin_density"))
    homo_score = 0.0 if somo is None else max(-5.0, min(5.0, (somo + 0.20) * 20.0))
    charge_score = 0.0 if charge is None else max(-3.0, min(3.0, -charge))
    spin_score = 0.0 if spin is None else max(-3.0, min(3.0, 3.0 - abs(spin - 1.0) * 3.0))
    return {
        "somo_or_homo_hartree_used": somo,
        "co_charge_used": charge,
        "co_spin_population_used": spin,
        "homo_score_from_somo_hartree": float(homo_score),
        "charge_score_from_co_charge": float(charge_score),
        "spin_score_from_co_spin_population": float(spin_score),
        "electronic_activation": float(homo_score + charge_score + spin_score),
        "provenance": electronic.get("provenance"),
    }


def geometry_descriptors(atoms: list[Atom]) -> dict:
    cobalt = _find_atoms(atoms, "Co")
    ps = _find_atoms(atoms, "P")
    os = _find_atoms(atoms, "O")
    heavy = [a for a in atoms if a[0].upper() != "H"]
    out: dict[str, Any] = {"atom_count": len(atoms)}
    if not cobalt:
        out.update({"valid_geometry": False, "reason": "no cobalt atom found"})
        return out
    co = cobalt[0]
    p_dists = sorted([_dist(co, p) for p in ps])[:2]
    o_dists = sorted([_dist(co, o) for o in os])[:2]
    bound_ps = [d for d in p_dists if 1.9 <= d <= 2.7]
    bound_os = [d for d in o_dists if 1.7 <= d <= 2.4]
    bite_angle = _angle(ps[0], co, ps[1]) if len(ps) >= 2 else None
    coord_atoms = []
    if len(ps) >= 2:
        coord_atoms.extend(sorted(ps, key=lambda a: _dist(co, a))[:2])
    if len(os) >= 2:
        coord_atoms.extend(sorted(os, key=lambda a: _dist(co, a))[:2])
    angles = [_angle(a, co, b) for a, b in combinations(coord_atoms, 2)]
    angles = [a for a in angles if a is not None]
    square_planar_distortion = min(
        1.0,
        sum(min(abs(a - 90.0), abs(a - 180.0)) for a in angles) / max(len(angles) * 45.0, 1.0),
    ) if angles else 1.0
    nonbonded = []
    for a, b in combinations(heavy, 2):
        d = _dist(a, b)
        if d > 0.1:
            nonbonded.append(d)
    min_heavy_distance = min(nonbonded) if nonbonded else None
    crowd_atoms = [a for a in heavy if a[0] not in {"Co", "P", "O"} and _dist(co, a) <= 3.5]
    crowding_score = len(crowd_atoms) + (0.0 if min_heavy_distance is None else max(0.0, 1.2 - min_heavy_distance) * 5.0)
    valid = len(bound_ps) >= 2 and len(bound_os) >= 2 and (min_heavy_distance is None or min_heavy_distance >= 0.65)
    out.update(
        {
            "valid_geometry": valid,
            "co_p_distances": p_dists,
            "co_o_distances": o_dists,
            "both_phosphines_coordinated": len(bound_ps) >= 2,
            "acac_coordinated": len(bound_os) >= 2,
            "co_p_asymmetry": abs(p_dists[0] - p_dists[1]) if len(p_dists) >= 2 else 9.9,
            "p_co_p_bite_angle": bite_angle,
            "square_planar_distortion": square_planar_distortion,
            "heavy_atoms_near_co_3p5A": len(crowd_atoms),
            "min_heavy_heavy_distance": min_heavy_distance,
            "steric_crowding_raw": crowding_score,
            "ligand_remains_bound": len(bound_ps) >= 2,
            "severe_collapse": min_heavy_distance is not None and min_heavy_distance < 0.65,
        }
    )
    return out


def objective_scores(validity: dict, geom: dict, electronic: dict) -> dict[str, float]:
    feasible = bool(validity.get("scf_converged") and validity.get("optimization_success") and geom.get("valid_geometry"))
    if not feasible:
        return {
            "electronic_activation": -100.0,
            "coordination_stability": -100.0,
            "chelate_geometry": -100.0,
            "steric_crowding": 100.0,
        }
    electronic_components = electronic_activation_components(electronic)
    p_asym = float(geom.get("co_p_asymmetry") or 9.9)
    stability = 10.0 - 10.0 * min(1.0, p_asym / 0.4)
    bite = geom.get("p_co_p_bite_angle")
    bite_penalty = 10.0 if bite is None else min(10.0, abs(float(bite) - 92.0) / 4.0)
    distortion = float(geom.get("square_planar_distortion") or 1.0)
    chelate = 10.0 - bite_penalty - 5.0 * distortion
    crowd = float(geom.get("steric_crowding_raw") or 0.0)
    return {
        "electronic_activation": float(electronic_components["electronic_activation"]),
        "coordination_stability": float(stability),
        "chelate_geometry": float(chelate),
        "steric_crowding": float(crowd),
    }
