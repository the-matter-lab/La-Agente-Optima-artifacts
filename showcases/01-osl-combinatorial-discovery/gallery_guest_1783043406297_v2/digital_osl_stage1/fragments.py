from __future__ import annotations

import itertools
import json
import math
from collections import deque
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors

from .config import PreparedStage, Stage1Config

REACTIVE_HALOGENS = {"Br", "I"}
FALLBACK_HALOGENS = {"Cl"}
CUSTOM_DESCRIPTOR_COLUMNS = [
    "heavy_atoms",
    "exact_mw",
    "hetero_atoms",
    "aromatic_rings",
    "rotatable_bonds",
    "tpsa",
    "clogp",
    "fraction_csp3",
]
PRODUCT_DESCRIPTOR_COLUMNS = [
    "heavy_atoms",
    "exact_mw",
    "hetero_atoms",
    "aromatic_rings",
    "rotatable_bonds",
    "tpsa",
    "clogp",
    "fraction_csp3",
    "ring_count",
]


class AssemblyError(RuntimeError):
    pass


def _canonical_nonisomeric_smiles(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise AssemblyError(f"RDKit failed to parse SMILES: {smiles}")
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)


def _component_atoms(mol: Chem.Mol, start_idx: int) -> set[int]:
    seen = {start_idx}
    queue = deque([start_idx])
    while queue:
        atom_idx = queue.popleft()
        atom = mol.GetAtomWithIdx(atom_idx)
        for neighbor in atom.GetNeighbors():
            neighbor_idx = neighbor.GetIdx()
            if neighbor_idx not in seen:
                seen.add(neighbor_idx)
                queue.append(neighbor_idx)
    return seen


def _delete_atoms(rwmol: Chem.RWMol, atom_indices: Iterable[int]) -> None:
    for atom_idx in sorted(set(atom_indices), reverse=True):
        rwmol.RemoveAtom(atom_idx)


def _reactive_halogen_indices(mol: Chem.Mol) -> list[int]:
    preferred = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() in REACTIVE_HALOGENS]
    if preferred:
        return preferred
    return [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() in FALLBACK_HALOGENS]


def _strip_boron_handle(smiles: str) -> tuple[Chem.Mol, int]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise AssemblyError(f"Could not parse boron-containing fragment: {smiles}")
    boron_atoms = [atom for atom in mol.GetAtoms() if atom.GetSymbol() == "B"]
    if len(boron_atoms) != 1:
        raise AssemblyError(f"Expected exactly one boron atom in fragment: {smiles}")
    boron_atom = boron_atoms[0]
    carbon_neighbors = [neighbor.GetIdx() for neighbor in boron_atom.GetNeighbors() if neighbor.GetSymbol() == "C"]
    if len(carbon_neighbors) != 1:
        raise AssemblyError(
            f"Expected exactly one carbon attachment to boron. Got {carbon_neighbors} for {smiles}"
        )
    anchor_idx = carbon_neighbors[0]
    editable = Chem.RWMol(mol)
    editable.RemoveBond(anchor_idx, boron_atom.GetIdx())
    detached = editable.GetMol()
    boron_component = _component_atoms(detached, boron_atom.GetIdx())
    editable = Chem.RWMol(detached)
    _delete_atoms(editable, boron_component)
    stripped = editable.GetMol()
    Chem.SanitizeMol(stripped)
    index_shift = sum(1 for idx in boron_component if idx < anchor_idx)
    return stripped, anchor_idx - index_shift


def _strip_single_reactive_halogen(mol: Chem.Mol) -> tuple[Chem.Mol, int]:
    reactive_halides = _reactive_halogen_indices(mol)
    if len(reactive_halides) != 1:
        raise AssemblyError(f"Expected exactly one reactive halogen after boron stripping: {Chem.MolToSmiles(mol)}")
    halide_idx = reactive_halides[0]
    halide_atom = mol.GetAtomWithIdx(halide_idx)
    neighbors = [neighbor.GetIdx() for neighbor in halide_atom.GetNeighbors() if neighbor.GetAtomicNum() > 1]
    if len(neighbors) != 1:
        raise AssemblyError(f"Reactive halogen had {len(neighbors)} heavy-atom neighbors: {Chem.MolToSmiles(mol)}")
    anchor_idx = neighbors[0]
    editable = Chem.RWMol(mol)
    editable.RemoveAtom(halide_idx)
    stripped = editable.GetMol()
    Chem.SanitizeMol(stripped)
    if halide_idx < anchor_idx:
        anchor_idx -= 1
    return stripped, anchor_idx


def _strip_two_reactive_halogens(smiles: str) -> tuple[Chem.Mol, list[int]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise AssemblyError(f"Could not parse dihalide core: {smiles}")
    reactive_halides = _reactive_halogen_indices(mol)
    if len(reactive_halides) != 2:
        raise AssemblyError(f"Expected exactly two reactive halogens in core: {smiles}")
    anchors: list[tuple[int, int]] = []
    for halide_idx in reactive_halides:
        neighbors = [neighbor.GetIdx() for neighbor in mol.GetAtomWithIdx(halide_idx).GetNeighbors() if neighbor.GetAtomicNum() > 1]
        if len(neighbors) != 1:
            raise AssemblyError(f"Core reactive halogen had {len(neighbors)} heavy-atom neighbors: {smiles}")
        anchors.append((halide_idx, neighbors[0]))
    editable = Chem.RWMol(mol)
    _delete_atoms(editable, reactive_halides)
    stripped = editable.GetMol()
    Chem.SanitizeMol(stripped)
    adjusted = []
    for halide_idx, anchor_idx in anchors:
        shift = sum(1 for other in reactive_halides if other < anchor_idx)
        adjusted.append(anchor_idx - shift)
    return stripped, adjusted


def _combine_with_single_bond(base_mol: Chem.Mol, fragment_mol: Chem.Mol, base_anchor: int, fragment_anchor: int) -> Chem.Mol:
    combined = Chem.CombineMols(base_mol, fragment_mol)
    editable = Chem.RWMol(combined)
    offset = base_mol.GetNumAtoms()
    editable.AddBond(base_anchor, offset + fragment_anchor, Chem.BondType.SINGLE)
    product = editable.GetMol()
    Chem.SanitizeMol(product)
    return product

def _prepare_bridge(bridge_smiles: str) -> tuple[Chem.Mol, int, int]:
    bridge_mol, bridge_boron_anchor = _strip_boron_handle(bridge_smiles)
    reactive_halides = _reactive_halogen_indices(bridge_mol)
    if len(reactive_halides) != 1:
        raise AssemblyError(f"Expected exactly one reactive halogen in bridge: {bridge_smiles}")
    halide_idx = reactive_halides[0]
    bridge_mol, bridge_halogen_anchor = _strip_single_reactive_halogen(bridge_mol)
    if halide_idx < bridge_boron_anchor:
        bridge_boron_anchor -= 1
    return bridge_mol, bridge_boron_anchor, bridge_halogen_anchor


def assemble_product_mol(cap_smiles: str, bridge_smiles: str, core_smiles: str) -> Chem.Mol:
    cap_mol, cap_anchor = _strip_boron_handle(cap_smiles)
    bridge_mol, bridge_boron_anchor, bridge_halogen_anchor = _prepare_bridge(bridge_smiles)
    core_mol, core_anchors = _strip_two_reactive_halogens(core_smiles)
    left_core_anchor, right_core_anchor = core_anchors

    product = core_mol
    product = _combine_with_single_bond(product, bridge_mol, left_core_anchor, bridge_boron_anchor)
    left_bridge_halogen_anchor = core_mol.GetNumAtoms() + bridge_halogen_anchor

    product = _combine_with_single_bond(product, bridge_mol, right_core_anchor, bridge_boron_anchor)
    right_bridge_halogen_anchor = core_mol.GetNumAtoms() + bridge_mol.GetNumAtoms() + bridge_halogen_anchor

    product = _combine_with_single_bond(product, cap_mol, left_bridge_halogen_anchor, cap_anchor)
    product = _combine_with_single_bond(product, cap_mol, right_bridge_halogen_anchor, cap_anchor)
    Chem.SanitizeMol(product)
    return product


def assemble_product_smiles(cap_smiles: str, bridge_smiles: str, core_smiles: str) -> str:
    product = assemble_product_mol(cap_smiles, bridge_smiles, core_smiles)
    return Chem.MolToSmiles(product, canonical=True, isomericSmiles=True)


def compute_smiles_descriptors(smiles: str) -> dict[str, float]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise AssemblyError(f"Could not parse SMILES for descriptor generation: {smiles}")
    ring_count = rdMolDescriptors.CalcNumRings(mol)
    return {
        "heavy_atoms": float(mol.GetNumHeavyAtoms()),
        "exact_mw": float(Descriptors.ExactMolWt(mol)),
        "hetero_atoms": float(rdMolDescriptors.CalcNumHeteroatoms(mol)),
        "aromatic_rings": float(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "rotatable_bonds": float(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "clogp": float(Crippen.MolLogP(mol)),
        "fraction_csp3": float(rdMolDescriptors.CalcFractionCSP3(mol)),
        "ring_count": float(ring_count),
        "halogen_count": float(sum(atom.GetSymbol() in {"F", "Cl", "Br", "I"} for atom in mol.GetAtoms())),
        "boron_count": float(sum(atom.GetSymbol() == "B" for atom in mol.GetAtoms())),
    }


def _prepare_catalog(path: Path, kind: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    expected_prefix = {"cap": "A", "bridge": "B", "core": "C"}[kind]
    if not all(str(hid).startswith(expected_prefix) for hid in df["hid"]):
        raise ValueError(f"Catalog {path} has identifiers that do not match prefix {expected_prefix}")
    descriptor_records = []
    reactive_site_records = []
    for row in df.itertuples(index=False):
        descriptors = compute_smiles_descriptors(row.smiles)
        descriptor_records.append(descriptors)
        try:
            if kind == "cap":
                _strip_boron_handle(row.smiles)
                reactive_site_records.append({"reactive_sites_ok": True, "reactive_note": "one boron handle"})
            elif kind == "bridge":
                stripped, _ = _strip_boron_handle(row.smiles)
                reactive_halides = _reactive_halogen_indices(stripped)
                reactive_site_records.append(
                    {
                        "reactive_sites_ok": len(reactive_halides) == 1,
                        "reactive_note": f"reactive halides after boron stripping={len(reactive_halides)}",
                    }
                )
            else:
                reactive_halides = _reactive_halogen_indices(Chem.MolFromSmiles(row.smiles))
                reactive_site_records.append(
                    {
                        "reactive_sites_ok": len(reactive_halides) == 2,
                        "reactive_note": f"reactive halides={len(reactive_halides)}",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            reactive_site_records.append({"reactive_sites_ok": False, "reactive_note": str(exc)})
    descriptor_df = pd.DataFrame(descriptor_records)
    reactive_df = pd.DataFrame(reactive_site_records)
    prepared = pd.concat([df.copy(), descriptor_df, reactive_df], axis=1)
    prepared["compatible_with_gen_2"] = prepared["compatible_with_gen_2"].astype(bool)
    prepared["size_rank_key"] = list(
        zip(
            prepared["heavy_atoms"],
            prepared["exact_mw"],
            prepared["rotatable_bonds"],
            prepared["hid"],
        )
    )
    return prepared.sort_values(["heavy_atoms", "exact_mw", "rotatable_bonds", "hid"]).reset_index(drop=True)


def validate_assembly_against_s6(
    caps: pd.DataFrame,
    bridges: pd.DataFrame,
    cores: pd.DataFrame,
    validation_catalog: Path,
) -> dict[str, Any]:
    cap_lookup = caps.set_index("hid")["smiles"].to_dict()
    bridge_lookup = bridges.set_index("hid")["smiles"].to_dict()
    core_lookup = cores.set_index("hid")["smiles"].to_dict()
    validation_df = pd.read_csv(validation_catalog)
    exact_matches = 0
    connectivity_matches = 0
    discrepancies: list[dict[str, Any]] = []
    for row in validation_df.itertuples(index=False):
        identifier = str(row.Identifier)
        cap_id, bridge_id, core_id = identifier[:4], identifier[4:8], identifier[8:12]
        generated = assemble_product_smiles(cap_lookup[cap_id], bridge_lookup[bridge_id], core_lookup[core_id])
        generated_exact = Chem.MolToSmiles(Chem.MolFromSmiles(generated), canonical=True, isomericSmiles=True)
        generated_connectivity = _canonical_nonisomeric_smiles(generated)
        reference_exact = Chem.MolToSmiles(Chem.MolFromSmiles(row.SMILES), canonical=True, isomericSmiles=True)
        reference_connectivity = _canonical_nonisomeric_smiles(row.SMILES)
        exact_ok = generated_exact == reference_exact
        connectivity_ok = generated_connectivity == reference_connectivity
        if exact_ok:
            exact_matches += 1
        if connectivity_ok:
            connectivity_matches += 1
        else:
            discrepancies.append(
                {
                    "identifier": identifier,
                    "generated_smiles_nonisomeric": generated_connectivity,
                    "reference_smiles_nonisomeric": reference_connectivity,
                }
            )
    return {
        "n_rows": int(len(validation_df)),
        "exact_smiles_matches": int(exact_matches),
        "connectivity_matches": int(connectivity_matches),
        "connectivity_match_fraction": float(connectivity_matches / len(validation_df)),
        "stereochemistry_only_mismatches": int(connectivity_matches - exact_matches),
        "hard_discrepancies": discrepancies[:20],
        "status": "passed" if connectivity_matches == len(validation_df) else "failed",
        "notes": [
            "Validation uses s6 only to verify fragment assembly, never for seeds or objective ranking.",
            "Reactive halogen inference prioritizes Br/I and only falls back to Cl, which preserves spectator chlorides seen in s6.",
        ],
    }


def _active_subset(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    active = df[df["compatible_with_gen_2"] & df["reactive_sites_ok"]].copy()
    active = active.sort_values(["heavy_atoms", "exact_mw", "rotatable_bonds", "hid"]).head(limit).reset_index(drop=True)
    if len(active) < 2:
        raise ValueError("Each active fragment catalog must contain at least 2 feasible entries for BO-MCP categorical parameters")
    return active


def _deduplicate_descriptor_rows(frame: pd.DataFrame, descriptor_columns: list[str]) -> list[str]:
    kept_columns = [column for column in descriptor_columns if frame[column].nunique(dropna=False) > 1]
    if not kept_columns:
        kept_columns = []
    rows = frame[kept_columns].round(8).apply(tuple, axis=1) if kept_columns else pd.Series([tuple()] * len(frame))
    if rows.nunique(dropna=False) != len(frame):
        kept_columns = list(kept_columns)
        frame = frame.copy()
        frame["identity_code"] = frame["hid"].str[1:].astype(float)
        kept_columns.append("identity_code")
    return kept_columns


def build_custom_descriptor_payload(frame: pd.DataFrame) -> tuple[dict[str, dict[str, float]], list[str]]:
    working = frame.copy()
    descriptor_columns = _deduplicate_descriptor_rows(working, CUSTOM_DESCRIPTOR_COLUMNS)
    if "identity_code" in descriptor_columns and "identity_code" not in working.columns:
        working["identity_code"] = working["hid"].str[1:].astype(float)
    if not descriptor_columns:
        working["identity_code"] = working["hid"].str[1:].astype(float)
        descriptor_columns = ["identity_code"]
    payload: dict[str, dict[str, float]] = {}
    for row in working.itertuples(index=False):
        payload[row.hid] = {column: float(getattr(row, column)) for column in descriptor_columns}
    return payload, descriptor_columns


def _representatives(active: pd.DataFrame, pool_size: int) -> list[str]:
    pool = active.head(min(pool_size, len(active))).copy()
    descriptor_cols = [col for col in PRODUCT_DESCRIPTOR_COLUMNS if pool[col].nunique(dropna=False) > 1]
    first = pool.iloc[0]["hid"]
    if len(pool) == 1:
        return [first]
    if not descriptor_cols:
        second = pool.iloc[1]["hid"]
        return [first, second]
    base = pool.iloc[0][descriptor_cols].astype(float)
    best_hid = None
    best_distance = -1.0
    for row in pool.iloc[1:].itertuples(index=False):
        current = pd.Series({col: float(getattr(row, col)) for col in descriptor_cols})
        distance = float(math.dist(base.tolist(), current.tolist()))
        if distance > best_distance:
            best_distance = distance
            best_hid = row.hid
    return [first, best_hid or pool.iloc[1]["hid"]]


def _build_candidate_record(
    cap_row: pd.Series,
    bridge_row: pd.Series,
    core_row: pd.Series,
    product_smiles: str,
    cap_id: str,
    bridge_id: str,
    core_id: str,
) -> dict[str, Any]:
    product_descriptors = compute_smiles_descriptors(product_smiles)
    candidate_id = f"{cap_id}{bridge_id}{core_id}"
    return {
        "candidate_id": candidate_id,
        "cap_id": cap_id,
        "bridge_id": bridge_id,
        "core_id": core_id,
        "product_smiles": product_smiles,
        "cap_smiles": cap_row["smiles"],
        "bridge_smiles": bridge_row["smiles"],
        "core_smiles": core_row["smiles"],
        "combined_heavy_atoms": float(product_descriptors["heavy_atoms"]),
        "combined_exact_mw": float(product_descriptors["exact_mw"]),
        "combined_rotatable_bonds": float(product_descriptors["rotatable_bonds"]),
        "combined_aromatic_rings": float(product_descriptors["aromatic_rings"]),
        "combined_hetero_atoms": float(product_descriptors["hetero_atoms"]),
        "combined_clogp": float(product_descriptors["clogp"]),
        "combined_fraction_csp3": float(product_descriptors["fraction_csp3"]),
        "combined_tpsa": float(product_descriptors["tpsa"]),
    }


def select_initial_candidates(
    active_caps: pd.DataFrame,
    active_bridges: pd.DataFrame,
    active_cores: pd.DataFrame,
    count: int,
    pool_size: int,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    cap_lookup = active_caps.set_index("hid")
    bridge_lookup = active_bridges.set_index("hid")
    core_lookup = active_cores.set_index("hid")
    cap_reps = _representatives(active_caps, pool_size)
    bridge_reps = _representatives(active_bridges, pool_size)
    core_reps = _representatives(active_cores, pool_size)

    proposed = [
        (cap_reps[0], bridge_reps[0], core_reps[0]),
        (cap_reps[1], bridge_reps[0], core_reps[1]),
        (cap_reps[0], bridge_reps[1], core_reps[1]),
        (cap_reps[1], bridge_reps[1], core_reps[0]),
        (cap_reps[1], bridge_reps[1], core_reps[1]),
        (cap_reps[0], bridge_reps[1], core_reps[0]),
    ]
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for cap_id, bridge_id, core_id in proposed:
        candidate_id = f"{cap_id}{bridge_id}{core_id}"
        if candidate_id in seen:
            continue
        product_smiles = assemble_product_smiles(
            cap_lookup.loc[cap_id, "smiles"],
            bridge_lookup.loc[bridge_id, "smiles"],
            core_lookup.loc[core_id, "smiles"],
        )
        selected.append(
            _build_candidate_record(
                cap_lookup.loc[cap_id],
                bridge_lookup.loc[bridge_id],
                core_lookup.loc[core_id],
                product_smiles,
                cap_id,
                bridge_id,
                core_id,
            )
        )
        seen.add(candidate_id)
        if len(selected) >= count:
            return selected

    for cap_id, bridge_id, core_id in itertools.product(active_caps["hid"], active_bridges["hid"], active_cores["hid"]):
        candidate_id = f"{cap_id}{bridge_id}{core_id}"
        if candidate_id in seen:
            continue
        product_smiles = assemble_product_smiles(
            cap_lookup.loc[cap_id, "smiles"],
            bridge_lookup.loc[bridge_id, "smiles"],
            core_lookup.loc[core_id, "smiles"],
        )
        selected.append(
            _build_candidate_record(
                cap_lookup.loc[cap_id],
                bridge_lookup.loc[bridge_id],
                core_lookup.loc[core_id],
                product_smiles,
                cap_id,
                bridge_id,
                core_id,
            )
        )
        seen.add(candidate_id)
        if len(selected) >= count:
            break
    return selected


def build_candidate_library(active_caps: pd.DataFrame, active_bridges: pd.DataFrame, active_cores: pd.DataFrame) -> pd.DataFrame:
    cap_lookup = active_caps.set_index("hid")
    bridge_lookup = active_bridges.set_index("hid")
    core_lookup = active_cores.set_index("hid")
    rows: list[dict[str, Any]] = []
    for cap_id, bridge_id, core_id in itertools.product(active_caps["hid"], active_bridges["hid"], active_cores["hid"]):
        product_smiles = assemble_product_smiles(
            cap_lookup.loc[cap_id, "smiles"],
            bridge_lookup.loc[bridge_id, "smiles"],
            core_lookup.loc[core_id, "smiles"],
        )
        rows.append(
            _build_candidate_record(
                cap_lookup.loc[cap_id],
                bridge_lookup.loc[bridge_id],
                core_lookup.loc[core_id],
                product_smiles,
                cap_id,
                bridge_id,
                core_id,
            )
        )
    library = pd.DataFrame(rows)
    return library.sort_values(["combined_heavy_atoms", "combined_exact_mw", "candidate_id"]).reset_index(drop=True)


def build_campaign_intake(config: Stage1Config, active_caps: pd.DataFrame, active_bridges: pd.DataFrame, active_cores: pd.DataFrame) -> tuple[dict[str, Any], str, dict[str, list[str]]]:
    cap_descriptors, cap_descriptor_columns = build_custom_descriptor_payload(active_caps)
    bridge_descriptors, bridge_descriptor_columns = build_custom_descriptor_payload(active_bridges)
    core_descriptors, core_descriptor_columns = build_custom_descriptor_payload(active_cores)

    parameter_payloads = [
        {
            "name": "cap_id",
            "type": "categorical",
            "categories": active_caps["hid"].tolist(),
            "parameter_options": {
                "baybe": {
                    "role": "custom",
                    "custom_descriptors": cap_descriptors,
                    "decorrelate": False,
                }
            },
        },
        {
            "name": "bridge_id",
            "type": "categorical",
            "categories": active_bridges["hid"].tolist(),
            "parameter_options": {
                "baybe": {
                    "role": "custom",
                    "custom_descriptors": bridge_descriptors,
                    "decorrelate": False,
                }
            },
        },
        {
            "name": "core_id",
            "type": "categorical",
            "categories": active_cores["hid"].tolist(),
            "parameter_options": {
                "baybe": {
                    "role": "custom",
                    "custom_descriptors": core_descriptors,
                    "decorrelate": False,
                }
            },
        },
    ]

    intake = {
        "name": config.campaign_name,
        "description": config.campaign_description,
        "backend": config.backend,
        "batch_size": config.batch_size,
        "random_seed": config.random_seed,
        "initial_design_size": 0,
        "parameters": parameter_payloads,
        "objectives": [
            {
                "name": "bright_osc_strength",
                "direction": "maximize",
                "unit": "dimensionless",
            },
            {
                "name": "color_error_ev",
                "direction": "minimize",
                "unit": "eV",
            },
            {
                "name": "ambiguity_penalty",
                "direction": "minimize",
                "unit": "arb",
            },
        ],
    }
    descriptor_columns = {
        "cap_id": cap_descriptor_columns,
        "bridge_id": bridge_descriptor_columns,
        "core_id": core_descriptor_columns,
    }
    return intake, config.backend, descriptor_columns


def build_plain_categorical_intake(config: Stage1Config, active_caps: pd.DataFrame, active_bridges: pd.DataFrame, active_cores: pd.DataFrame) -> tuple[dict[str, Any], str]:
    intake = {
        "name": config.campaign_name,
        "description": config.campaign_description,
        "backend": config.backend,
        "batch_size": config.batch_size,
        "random_seed": config.random_seed,
        "initial_design_size": 0,
        "parameters": [
            {"name": "cap_id", "type": "categorical", "categories": active_caps["hid"].tolist()},
            {"name": "bridge_id", "type": "categorical", "categories": active_bridges["hid"].tolist()},
            {"name": "core_id", "type": "categorical", "categories": active_cores["hid"].tolist()},
        ],
        "objectives": [
            {"name": "bright_osc_strength", "direction": "maximize", "unit": "dimensionless"},
            {"name": "color_error_ev", "direction": "minimize", "unit": "eV"},
            {"name": "ambiguity_penalty", "direction": "minimize", "unit": "arb"},
        ],
    }
    return intake, "plain-categorical-fallback"


def prepare_stage(config: Stage1Config) -> PreparedStage:
    materialized = config.materialize()
    caps = _prepare_catalog(materialized.cap_catalog, "cap")
    bridges = _prepare_catalog(materialized.bridge_catalog, "bridge")
    cores = _prepare_catalog(materialized.core_catalog, "core")
    validation_report = validate_assembly_against_s6(caps, bridges, cores, materialized.validation_catalog)
    if validation_report["status"] != "passed":
        raise AssemblyError(json.dumps(validation_report, indent=2))

    active_caps = _active_subset(caps, materialized.cap_limit)
    active_bridges = _active_subset(bridges, materialized.bridge_limit)
    active_cores = _active_subset(cores, materialized.core_limit)
    candidate_library = build_candidate_library(active_caps, active_bridges, active_cores)
    initial_candidates = select_initial_candidates(
        active_caps,
        active_bridges,
        active_cores,
        count=materialized.initial_observation_count,
        pool_size=materialized.seed_diversity_pool,
    )
    intake, intake_backend, descriptor_columns = build_campaign_intake(materialized, active_caps, active_bridges, active_cores)
    preview_summary = {
        "assembly_validation": validation_report,
        "active_fragment_counts": {
            "caps": int(len(active_caps)),
            "bridges": int(len(active_bridges)),
            "cores": int(len(active_cores)),
            "candidate_count": int(len(candidate_library)),
        },
        "active_fragments": {
            "caps": active_caps[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
            "bridges": active_bridges[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
            "cores": active_cores[["hid", "smiles", "heavy_atoms", "exact_mw"]].to_dict(orient="records"),
        },
        "initial_candidates": initial_candidates,
        "descriptor_columns": descriptor_columns,
        "intake": intake,
    }
    return PreparedStage(
        config=materialized,
        cap_catalog=caps,
        bridge_catalog=bridges,
        core_catalog=cores,
        validation_report=validation_report,
        active_caps=active_caps,
        active_bridges=active_bridges,
        active_cores=active_cores,
        candidate_library=candidate_library,
        initial_candidates=initial_candidates,
        intake=intake,
        intake_backend=intake_backend,
        preview_summary=preview_summary,
    )
