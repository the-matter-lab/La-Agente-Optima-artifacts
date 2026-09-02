from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import logfire
import pandas as pd
import requests
from grafico.deps import GraficoDeps
from product_smiles import DigitalOslProductSmiles
from rdkit import Chem
from rdkit.Chem import AllChem

from domains.pyscf.tools.conversion_tools import UnitConvPair, get_conversion_factor
from domains.pyscf.tools.pyscf_workflow_tools import run_pyscf_workflow

logfire.configure()
logfire.instrument_requests()

LEVEL_OF_THEORY = "RDKit ETKDG/MMFF conformer // PBE/3-21G + TDA(3)"
DEFAULT_CAMPAIGN_PREFIX = "smallest-fragments-digital-osl-bo-continuation"
DEFAULT_PREDECESSOR_CAMPAIGN_ID = "d661d8e6-34c2-476f-a065-4c485509e50f"
DEFAULT_PREDECESSOR_EXPORT = "artifacts/run_20260630-195356/campaign_export.csv"


@dataclass(frozen=True)
class BuildingBlock:
    hid: str
    smiles: str
    heavy_atoms: int
    total_atoms: int
    smiles_length: int
    rank: int


@dataclass(frozen=True)
class Candidate:
    cap_id: str
    bridge_id: str
    core_id: str

    @property
    def tuple_id(self) -> str:
        return f"{self.cap_id}_{self.bridge_id}_{self.core_id}"


class CampaignRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.workspace = Path(args.catalog_dir).resolve()
        self.run_nonce = uuid.uuid4().hex[:12]
        self.timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.api_base = self._get_required_env("BO_MCP_API_URL", default="http://api:8000").rstrip("/")
        self.api_key = self._get_required_env("BO_MCP_API_KEY")
        artifact_name = args.artifact_dir or f"artifacts/{DEFAULT_CAMPAIGN_PREFIX}_{self.timestamp}_{self.run_nonce}"
        self.artifact_dir = Path(artifact_name)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.api_dir = self.artifact_dir / "api"
        self.eval_dir = self.artifact_dir / "evaluations"
        self.api_dir.mkdir(exist_ok=True)
        self.eval_dir.mkdir(exist_ok=True)
        self.ctx = SimpleNamespace(
            deps=GraficoDeps(
                ws_url=os.getenv("GRAPHCHAT_AGENT_WS_URL") or os.getenv("VITE_WS_URL", "ws://graphchat:3000"),
                room=os.getenv("GRAPHCHAT_ROOM", "room"),
                sparql_endpoint=os.getenv("SPARQL_ENDPOINT", "http://blazegraph:8080/blazegraph/namespace/kb/sparql"),
            )
        )
        self.generator = DigitalOslProductSmiles.from_default_catalogs(self.workspace)
        self.predecessor_campaign_id = args.predecessor_campaign_id
        self.predecessor_export_path = Path(args.predecessor_export)
        self.successor_campaign_id: str | None = None
        self.seeded_results: list[dict[str, Any]] = []
        self.live_successful_results: list[dict[str, Any]] = []
        self.all_successful_results: list[dict[str, Any]] = []
        self.evaluated_tuples: set[tuple[str, str, str]] = set()
        self.live_attempted = 0
        self.live_failed = 0
        self.duplicate_suggestions = 0
        self.rejected_suggestions = 0

    @staticmethod
    def _get_required_env(name: str, default: str | None = None) -> str:
        value = os.getenv(name, default)
        if value:
            return value
        raise RuntimeError(f"Missing required environment variable: {name}")

    def run(self) -> int:
        active_space = self._build_active_space()
        seed_rows = self._load_seed_rows(active_space)
        intake = self._build_campaign_intake(active_space, seed_count=len(seed_rows))
        self._write_json(self.artifact_dir / "campaign_intake.json", intake)
        self._validate_intake(intake)
        self.successor_campaign_id = self._create_campaign(intake)
        try:
            self._seed_successor_campaign(seed_rows)
            while self.live_attempted < self.args.total_live_evaluations:
                batch_number = (self.live_attempted // self.args.batch_size) + 1
                suggestions = self._acquire_unique_suggestions(active_space, self.args.batch_size, batch_number)
                if not suggestions:
                    raise RuntimeError("No usable BO suggestions were available before reaching the requested live evaluation count.")
                print(
                    f"continuation_batch {batch_number}: evaluating {len(suggestions)} candidates "
                    f"({self.live_attempted}/{self.args.total_live_evaluations} completed so far)"
                )
                self._evaluate_live_batch(suggestions)
        finally:
            self._export_campaign_if_available()
            if self.successor_campaign_id and self.args.terminate_on_exit:
                self._terminate_campaign()
            self._write_final_report(active_space)
        return 0

    def _build_active_space(self) -> dict[str, list[BuildingBlock]]:
        active_space = {
            "caps": self._load_filtered_catalog("adk9227_data_s1.csv", self.args.cap_limit),
            "bridges": self._load_filtered_catalog("adk9227_data_s2.csv", self.args.bridge_limit),
            "cores": self._load_filtered_catalog("adk9227_data_s3.csv", self.args.core_limit),
        }
        summary = {name: [block.__dict__ for block in blocks] for name, blocks in active_space.items()}
        self._write_json(self.artifact_dir / "active_space.json", summary)
        for name, blocks in active_space.items():
            self._write_csv(
                self.artifact_dir / f"active_space_{name}.csv",
                fieldnames=["hid", "smiles", "heavy_atoms", "total_atoms", "smiles_length", "rank"],
                rows=[block.__dict__ for block in blocks],
            )
        return active_space

    def _load_filtered_catalog(self, filename: str, limit: int) -> list[BuildingBlock]:
        data = pd.read_csv(self.workspace / filename)
        ranked: list[BuildingBlock] = []
        for _, row in data.iterrows():
            smiles = str(row["smiles"])
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise RuntimeError(f"Invalid building-block SMILES in {filename}: {row['hid']} -> {smiles}")
            ranked.append(
                BuildingBlock(
                    hid=str(row["hid"]),
                    smiles=smiles,
                    heavy_atoms=mol.GetNumHeavyAtoms(),
                    total_atoms=mol.GetNumAtoms(),
                    smiles_length=len(smiles),
                    rank=-1,
                )
            )
        ranked.sort(key=lambda block: (block.heavy_atoms, block.total_atoms, block.smiles_length, block.smiles, block.hid))
        trimmed = ranked[: min(limit, len(ranked))]
        return [
            BuildingBlock(
                hid=block.hid,
                smiles=block.smiles,
                heavy_atoms=block.heavy_atoms,
                total_atoms=block.total_atoms,
                smiles_length=block.smiles_length,
                rank=index,
            )
            for index, block in enumerate(trimmed)
        ]

    def _load_seed_rows(self, active_space: dict[str, list[BuildingBlock]]) -> list[dict[str, Any]]:
        path = self.predecessor_export_path
        if not path.exists():
            raise RuntimeError(f"Predecessor export CSV not found: {path}")
        allowed = {
            "cap_id": {block.hid for block in active_space["caps"]},
            "bridge_id": {block.hid for block in active_space["bridges"]},
            "core_id": {block.hid for block in active_space["cores"]},
        }
        seen: set[tuple[str, str, str]] = set()
        seed_rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=2):
                candidate = Candidate(
                    cap_id=str(row["param_cap_id"]),
                    bridge_id=str(row["param_bridge_id"]),
                    core_id=str(row["param_core_id"]),
                )
                candidate_key = (candidate.cap_id, candidate.bridge_id, candidate.core_id)
                if candidate_key in seen:
                    continue
                seen.add(candidate_key)
                if candidate.cap_id not in allowed["cap_id"] or candidate.bridge_id not in allowed["bridge_id"] or candidate.core_id not in allowed["core_id"]:
                    raise RuntimeError(
                        f"Seed tuple {candidate.tuple_id} from predecessor export is outside the reconstructed active space. "
                        "The continuation run must match the original filtered space."
                    )
                objective_values = {
                    "max_oscillator_strength_s1_s3": float(row["obj_max_oscillator_strength_s1_s3"]),
                    "color_error_eV": float(row["obj_color_error_eV"]),
                    "conformational_ambiguity": float(row["obj_conformational_ambiguity"]),
                }
                if not all(math.isfinite(value) for value in objective_values.values()):
                    raise RuntimeError(f"Seed row {row_index} contains non-finite objectives: {candidate.tuple_id}")
                seed_rows.append(
                    {
                        "candidate": candidate,
                        "parameter_values": {
                            "cap_id": candidate.cap_id,
                            "bridge_id": candidate.bridge_id,
                            "core_id": candidate.core_id,
                        },
                        "objective_values": objective_values,
                        "metadata": {
                            "batch_ref": f"predecessor:{self.predecessor_campaign_id}",
                            "source_file": str(path),
                            "source_row": row_index,
                            "notes": f"Seeded from terminated predecessor campaign {self.predecessor_campaign_id}",
                            "conditions": {
                                "level_of_theory": LEVEL_OF_THEORY,
                                "predecessor_campaign_id": self.predecessor_campaign_id,
                            },
                        },
                    }
                )
        if len(seed_rows) != self.args.expected_seed_count:
            raise RuntimeError(
                f"Expected {self.args.expected_seed_count} successful seed rows in {path}, found {len(seed_rows)}."
            )
        self._write_json(
            self.artifact_dir / "seed_rows.json",
            [
                {
                    "tuple_id": item["candidate"].tuple_id,
                    "parameter_values": item["parameter_values"],
                    "objective_values": item["objective_values"],
                    "metadata": item["metadata"],
                }
                for item in seed_rows
            ],
        )
        return seed_rows

    def _build_campaign_intake(self, active_space: dict[str, list[BuildingBlock]], seed_count: int) -> dict[str, Any]:
        name = self.args.campaign_name or f"{DEFAULT_CAMPAIGN_PREFIX}-{self.timestamp}-{self.run_nonce}"
        description = (
            "Successor campaign for a terminated Digital OSL BO/PySCF run. "
            "The predecessor campaign is not resumed directly; instead, its completed observations are reseeded from a CSV export, "
            "then new BO suggestions are evaluated in batches of 2 over the same dynamically filtered smallest-fragment active space."
        )
        return {
            "name": name,
            "description": description,
            "backend": "baybe",
            "batch_size": self.args.batch_size,
            "initial_design_size": 0,
            "max_iterations": self.args.total_live_evaluations,
            "max_observations": seed_count + self.args.total_live_evaluations,
            "random_seed": self.args.random_seed,
            "parameters": [
                self._substance_parameter("cap_id", active_space["caps"]),
                self._substance_parameter("bridge_id", active_space["bridges"]),
                self._substance_parameter("core_id", active_space["cores"]),
            ],
            "objectives": [
                {"name": "max_oscillator_strength_s1_s3", "direction": "maximize"},
                {"name": "color_error_eV", "direction": "minimize"},
                {"name": "conformational_ambiguity", "direction": "minimize"},
            ],
        }

    @staticmethod
    def _substance_parameter(name: str, blocks: list[BuildingBlock]) -> dict[str, Any]:
        return {
            "name": name,
            "type": "categorical",
            "categories": [block.hid for block in blocks],
            "parameter_options": {
                "baybe": {
                    "role": "substance",
                    "substance_data": {block.hid: block.smiles for block in blocks},
                }
            },
        }

    def _seed_successor_campaign(self, seed_rows: list[dict[str, Any]]) -> None:
        assert self.successor_campaign_id
        payload = {
            "source": "api",
            "results": [
                {
                    "parameter_values": item["parameter_values"],
                    "objective_values": item["objective_values"],
                    "metadata": item["metadata"],
                }
                for item in seed_rows
            ],
        }
        response = self._request_json(
            "post",
            f"/api/v1/results/{self.successor_campaign_id}",
            json_body=payload,
            extra_headers={"Idempotency-Key": self._idempotency_key("seed-results")},
            artifact_name="seed_results_response.json",
        )
        if not response.get("success"):
            raise RuntimeError(f"Seed result submission failed: {response.get('errors')} / {response.get('field_errors')}")
        self.seeded_results = [
            {
                "tuple_id": item["candidate"].tuple_id,
                "parameter_values": item["parameter_values"],
                "objective_values": item["objective_values"],
                "seeded": True,
            }
            for item in seed_rows
        ]
        self.all_successful_results.extend(self.seeded_results)
        for item in seed_rows:
            candidate = item["candidate"]
            self.evaluated_tuples.add((candidate.cap_id, candidate.bridge_id, candidate.core_id))
        print(
            f"seeded_successor_campaign: {len(seed_rows)} completed predecessor results copied into successor {self.successor_campaign_id}"
        )
        logfire.info(
            "Seeded successor campaign",
            predecessor_campaign_id=self.predecessor_campaign_id,
            successor_campaign_id=self.successor_campaign_id,
            seeded_results=len(seed_rows),
        )

    def _acquire_unique_suggestions(
        self,
        active_space: dict[str, list[BuildingBlock]],
        needed: int,
        batch_number: int,
    ) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        local_seen: set[tuple[str, str, str]] = set()
        source_rounds = 0
        while len(unique) < needed:
            candidates = self._list_pending_suggestions() if source_rounds == 0 else self._generate_suggestions(batch_number)
            source_rounds += 1
            if not candidates:
                if source_rounds == 1:
                    continue
                if unique:
                    raise RuntimeError("Unable to top up a full unique batch after duplicate/pending filtering.")
                return []
            for suggestion in candidates:
                candidate = self._candidate_from_parameter_values(suggestion["parameter_values"])
                candidate_key = (candidate.cap_id, candidate.bridge_id, candidate.core_id)
                if not self._candidate_in_active_space(candidate, active_space):
                    self._reject_suggestion(suggestion["id"], "outside_active_space")
                    raise RuntimeError(f"BO suggested tuple outside the filtered active space: {candidate.tuple_id}")
                if candidate_key in self.evaluated_tuples or candidate_key in local_seen:
                    self._reject_suggestion(suggestion["id"], "duplicate_tuple")
                    self.duplicate_suggestions += 1
                    continue
                unique.append(suggestion)
                local_seen.add(candidate_key)
                if len(unique) >= needed:
                    break
            if source_rounds > self.args.max_suggestion_rounds_per_batch and len(unique) < needed:
                raise RuntimeError("Too many duplicate/pending suggestion rounds while assembling a BO batch.")
        return unique

    def _list_pending_suggestions(self) -> list[dict[str, Any]]:
        assert self.successor_campaign_id
        response = requests.get(
            f"{self.api_base}/api/v1/suggestions/{self.successor_campaign_id}",
            headers=self._headers(),
            params={"status": "pending"},
            timeout=self.args.request_timeout_s,
        )
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Non-JSON response from pending-suggestions query: {response.text[:500]}") from exc
        self._write_json(self.api_dir / f"pending_suggestions_{self.live_attempted:03d}.json", {"status_code": response.status_code, "body": data})
        if response.status_code >= 400:
            raise RuntimeError(f"Pending suggestion query failed with HTTP {response.status_code}: {data}")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected pending suggestion payload: {data}")
        return data

    def _generate_suggestions(self, batch_number: int) -> list[dict[str, Any]]:
        assert self.successor_campaign_id
        response = self._request_json(
            "post",
            f"/api/v1/suggestions/{self.successor_campaign_id}/generate",
            params={"batch_size": self.args.batch_size},
            artifact_name=f"suggestions_generate_batch_{batch_number:03d}_attempt_{self.live_attempted:03d}.json",
        )
        if not response.get("success"):
            errors = response.get("errors") or []
            message = " | ".join(str(item) for item in errors)
            if any("stopping criteria" in str(item).lower() or "max_" in str(item).lower() for item in errors):
                logfire.info("Suggestion generation stopped cleanly", successor_campaign_id=self.successor_campaign_id, errors=message)
                return []
            raise RuntimeError(f"Suggestion generation failed: {errors}")
        suggestions = response.get("suggestions") or []
        if not isinstance(suggestions, list):
            raise RuntimeError(f"Unexpected suggestions payload: {response}")
        return suggestions

    def _evaluate_live_batch(self, suggestions: list[dict[str, Any]]) -> None:
        successes: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(suggestions)) as executor:
            future_map = {
                executor.submit(
                    self._evaluate_candidate,
                    self._candidate_from_parameter_values(suggestion["parameter_values"]),
                    stage="live",
                    live_index=self.live_attempted + index,
                ): suggestion
                for index, suggestion in enumerate(suggestions, start=1)
            }
            for future in as_completed(future_map):
                suggestion = future_map[future]
                candidate = self._candidate_from_parameter_values(suggestion["parameter_values"])
                candidate_key = (candidate.cap_id, candidate.bridge_id, candidate.core_id)
                self.live_attempted += 1
                self.evaluated_tuples.add(candidate_key)
                result = future.result()
                if result is None:
                    self.live_failed += 1
                    self._reject_suggestion(suggestion["id"], "evaluation_failed")
                    continue
                result["suggestion_id"] = suggestion["id"]
                successes.append(result)
                self.live_successful_results.append(result)
                self.all_successful_results.append(result)
        if successes:
            self._submit_results(successes)

    def _evaluate_candidate(
        self,
        candidate: Candidate,
        stage: str,
        live_index: int | None,
    ) -> dict[str, Any] | None:
        prefix = f"{stage}_{live_index or len(self.live_successful_results) + self.live_failed + 1:03d}_{candidate.tuple_id}"
        candidate_dir = self.eval_dir / prefix
        candidate_dir.mkdir(parents=True, exist_ok=True)
        logfire.info("Evaluating candidate", candidate=candidate.tuple_id, stage=stage)
        try:
            smiles = self.generator.generate(candidate.cap_id, candidate.bridge_id, candidate.core_id)
            self._write_text(candidate_dir / "product.smiles", smiles + "\n")
            if self.args.synthetic_evaluator:
                result = self._synthetic_result(candidate, smiles)
                self._write_json(candidate_dir / "result.json", result)
                return result
            conformer_data = self._build_lowest_energy_conformer(smiles, candidate_dir)
            pyscf_result = self._run_pyscf(xyz=conformer_data["xyz"], candidate_dir=candidate_dir)
            result = self._build_result_record(candidate, smiles, conformer_data, pyscf_result)
            self._write_json(candidate_dir / "result.json", result)
            return result
        except Exception as exc:
            logfire.info("Candidate evaluation failed", candidate=candidate.tuple_id, stage=stage, error=str(exc))
            self._write_json(
                candidate_dir / "failure.json",
                {
                    "candidate": candidate.__dict__,
                    "stage": stage,
                    "error": str(exc),
                },
            )
            return None

    def _build_lowest_energy_conformer(self, smiles: str, candidate_dir: Path) -> dict[str, Any]:
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        if mol is None:
            raise RuntimeError("RDKit could not parse generated product SMILES")
        params = AllChem.ETKDGv3()
        params.randomSeed = self.args.rdkit_seed
        conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=self.args.num_conformers, params=params))
        if not conf_ids:
            raise RuntimeError("RDKit ETKDG failed to generate any conformers")
        mmff_props = AllChem.MMFFGetMoleculeProperties(mol)
        if mmff_props is None:
            raise RuntimeError("MMFF parameters unavailable for generated product")
        conformers: list[dict[str, float | int]] = []
        for conf_id in conf_ids:
            optimize_status = AllChem.MMFFOptimizeMolecule(mol, confId=conf_id)
            force_field = AllChem.MMFFGetMoleculeForceField(mol, mmff_props, confId=conf_id)
            if force_field is None:
                raise RuntimeError("MMFF force field construction failed")
            energy = float(force_field.CalcEnergy())
            conformers.append({"conf_id": int(conf_id), "energy_kcal_per_mol": energy, "optimize_status": int(optimize_status)})
        conformers.sort(key=lambda item: item["energy_kcal_per_mol"])
        best = conformers[0]
        min_energy = float(best["energy_kcal_per_mol"])
        ambiguity = sum(1 for item in conformers if float(item["energy_kcal_per_mol"]) <= min_energy + self.args.ambiguity_window_kcal)
        xyz = self._conformer_to_xyz(mol, int(best["conf_id"]))
        self._write_json(
            candidate_dir / "conformers.json",
            {
                "conformers": conformers,
                "ambiguity_window_kcal": self.args.ambiguity_window_kcal,
                "conformational_ambiguity": ambiguity,
            },
        )
        self._write_text(candidate_dir / "selected_conformer.xyz", xyz)
        writer = Chem.SDWriter(str(candidate_dir / "selected_conformer.sdf"))
        writer.write(mol, confId=int(best["conf_id"]))
        writer.close()
        return {
            "xyz": xyz,
            "best_conf_id": int(best["conf_id"]),
            "best_energy_kcal_per_mol": min_energy,
            "conformational_ambiguity": int(ambiguity),
        }

    @staticmethod
    def _conformer_to_xyz(mol: Chem.Mol, conf_id: int) -> str:
        conformer = mol.GetConformer(conf_id)
        lines = [str(mol.GetNumAtoms()), f"rdkit_etkdg_mmff_conf_{conf_id}"]
        for atom in mol.GetAtoms():
            point = conformer.GetAtomPosition(atom.GetIdx())
            lines.append(f"{atom.GetSymbol()} {point.x:.8f} {point.y:.8f} {point.z:.8f}")
        return "\n".join(lines) + "\n"

    def _run_pyscf(self, xyz: str, candidate_dir: Path) -> dict[str, Any]:
        result = run_pyscf_workflow(
            self.ctx,
            summarised_user_query=(
                "RKS PBE/3-21G single point on the supplied geometry, followed by 3-state singlet TDA-TDDFT "
                "and molecular analysis. Do not optimize geometry or run frequencies."
            ),
            identifier_type="xyz",
            identifier=xyz,
            basis_set="3-21g",
            xc_functional="pbe",
            restricted=True,
            exit_node="MolecularAnalysis",
            tddft_nstates=3,
            workflow_timeout_s=self.args.pyscf_timeout_s,
        )
        dumped = result.model_dump(mode="json")
        self._write_json(candidate_dir / "pyscf_result.json", dumped)
        return dumped

    def _build_result_record(
        self,
        candidate: Candidate,
        smiles: str,
        conformer_data: dict[str, Any],
        pyscf_result: dict[str, Any],
    ) -> dict[str, Any]:
        total_energy = pyscf_result.get("total_energy")
        if not isinstance(total_energy, (int, float)) or not math.isfinite(total_energy):
            raise RuntimeError("PySCF total_energy missing or non-finite")
        tddft_results = pyscf_result.get("tddft_results") or {}
        singlet_energies = tddft_results.get("tddft_singlet_energies") or tddft_results.get("tddft_energies")
        singlet_osc = tddft_results.get("tddft_singlet_oscillator_strength") or tddft_results.get("tddft_oscillator_strength")
        if not isinstance(singlet_energies, list) or len(singlet_energies) < 3:
            raise RuntimeError("PySCF singlet excitation energies missing")
        if not isinstance(singlet_osc, list) or len(singlet_osc) < 3:
            raise RuntimeError("PySCF singlet oscillator strengths missing")
        analysis_results = pyscf_result.get("analysis_results") or {}
        if not isinstance(analysis_results, dict) or not analysis_results:
            raise RuntimeError("PySCF molecular analysis results missing")
        converted = get_conversion_factor(
            UnitConversionPairs=[UnitConvPair(value=float(energy), from_unit="hartree", to_unit="eV") for energy in singlet_energies[:3]]
        )
        if not isinstance(converted, list) or len(converted) != 3:
            raise RuntimeError(f"Failed to convert singlet energies to eV: {converted}")
        singlet_energies_ev = [float(value) for value in converted]
        oscillator_strengths = [float(value) for value in singlet_osc[:3]]
        if not all(math.isfinite(value) for value in singlet_energies_ev + oscillator_strengths):
            raise RuntimeError("Non-finite TDDFT values encountered")
        objective_values = {
            "max_oscillator_strength_s1_s3": max(oscillator_strengths),
            "color_error_eV": min(abs(value - self.args.e_target_ev) for value in singlet_energies_ev),
            "conformational_ambiguity": float(conformer_data["conformational_ambiguity"]),
        }
        if not all(math.isfinite(float(value)) for value in objective_values.values()):
            raise RuntimeError("Objective values contain non-finite numbers")
        return {
            "tuple_id": candidate.tuple_id,
            "parameter_values": {
                "cap_id": candidate.cap_id,
                "bridge_id": candidate.bridge_id,
                "core_id": candidate.core_id,
            },
            "objective_values": {key: float(value) for key, value in objective_values.items()},
            "metadata": {
                "level_of_theory": LEVEL_OF_THEORY,
            },
            "submission_metadata": {
                "conditions": {
                    "level_of_theory": LEVEL_OF_THEORY,
                    "e_target_eV": self.args.e_target_ev,
                    "best_conformer_energy_kcal_per_mol": float(conformer_data["best_energy_kcal_per_mol"]),
                    "selected_conformer_id": int(conformer_data["best_conf_id"]),
                    "tddft_singlet_energies_eV": ",".join(f"{value:.6f}" for value in singlet_energies_ev),
                    "tddft_singlet_oscillator_strengths": ",".join(f"{value:.6f}" for value in oscillator_strengths),
                    "total_energy_hartree": float(total_energy),
                },
                "notes": f"{candidate.cap_id}-{candidate.bridge_id}-{candidate.core_id}",
            },
            "smiles": smiles,
        }

    def _synthetic_result(self, candidate: Candidate, smiles: str) -> dict[str, Any]:
        cap_score = int(candidate.cap_id[1:])
        bridge_score = int(candidate.bridge_id[1:])
        core_score = int(candidate.core_id[1:])
        pseudo_energy = 1.8 + ((len(smiles) + cap_score + bridge_score + core_score) % 12) * 0.12
        return {
            "tuple_id": candidate.tuple_id,
            "parameter_values": {
                "cap_id": candidate.cap_id,
                "bridge_id": candidate.bridge_id,
                "core_id": candidate.core_id,
            },
            "objective_values": {
                "max_oscillator_strength_s1_s3": float(1.0 / (1 + (cap_score % 5) + (bridge_score % 3) + (core_score % 7))),
                "color_error_eV": float(abs(pseudo_energy - self.args.e_target_ev)),
                "conformational_ambiguity": float(1 + ((cap_score + bridge_score + core_score) % 3)),
            },
            "metadata": {
                "level_of_theory": "synthetic_validation_only",
            },
            "submission_metadata": {
                "conditions": {
                    "level_of_theory": "synthetic_validation_only",
                },
                "notes": f"synthetic evaluator for {candidate.cap_id}-{candidate.bridge_id}-{candidate.core_id}",
            },
            "smiles": smiles,
        }

    def _validate_intake(self, intake: dict[str, Any]) -> None:
        response = self._request_json("post", "/api/v1/campaigns/validate", json_body={"intake": intake}, artifact_name="validate_response.json")
        if not response.get("valid"):
            raise RuntimeError(f"Campaign intake validation failed: {response.get('errors')}")

    def _create_campaign(self, intake: dict[str, Any]) -> str:
        response = self._request_json(
            "post",
            "/api/v1/campaigns",
            json_body={"intake": intake},
            extra_headers={"Idempotency-Key": self._idempotency_key("campaign-create")},
            artifact_name="create_campaign_response.json",
        )
        if not response.get("success"):
            raise RuntimeError(f"Campaign creation failed: {response.get('errors')}")
        campaign_id = response.get("campaign_id")
        if not campaign_id:
            raise RuntimeError("Campaign creation succeeded without a campaign_id")
        logfire.info("Created successor campaign", campaign_id=campaign_id)
        return str(campaign_id)

    def _submit_results(self, results: list[dict[str, Any]]) -> None:
        assert self.successor_campaign_id
        payload = {
            "source": "api",
            "results": [
                {
                    "parameter_values": result["parameter_values"],
                    "objective_values": result["objective_values"],
                    "metadata": result["submission_metadata"],
                    **({"suggestion_id": result["suggestion_id"]} if result.get("suggestion_id") else {}),
                }
                for result in results
            ],
        }
        response = self._request_json(
            "post",
            f"/api/v1/results/{self.successor_campaign_id}",
            json_body=payload,
            extra_headers={"Idempotency-Key": self._idempotency_key(f"results-{self.live_attempted:03d}")},
            artifact_name=f"submit_results_{self.live_attempted:03d}.json",
        )
        if not response.get("success"):
            raise RuntimeError(f"Result submission failed: {response.get('errors')} / {response.get('field_errors')}")

    def _reject_suggestion(self, suggestion_id: str, reason: str) -> None:
        response = self._request_json(
            "post",
            f"/api/v1/suggestions/{suggestion_id}/status",
            json_body={"status": "rejected"},
            artifact_name=f"reject_{suggestion_id}.json",
        )
        if not response.get("success"):
            raise RuntimeError(f"Failed to reject suggestion {suggestion_id}: {response.get('errors')}")
        self.rejected_suggestions += 1
        self._write_json(self.eval_dir / f"rejected_{suggestion_id}.json", {"suggestion_id": suggestion_id, "reason": reason})

    def _terminate_campaign(self) -> None:
        assert self.successor_campaign_id
        response = self._request_json(
            "post",
            f"/api/v1/campaigns/{self.successor_campaign_id}/lifecycle",
            json_body={"action": "terminate"},
            artifact_name="terminate_campaign_response.json",
        )
        if not response.get("success"):
            raise RuntimeError(f"Campaign termination failed: {response.get('errors')}")

    def _export_campaign_if_available(self) -> None:
        if not self.successor_campaign_id:
            return
        response = requests.get(
            f"{self.api_base}/api/v1/campaigns/{self.successor_campaign_id}/export",
            headers=self._headers(),
            params={"format": "csv"},
            timeout=self.args.request_timeout_s,
        )
        if response.status_code >= 400:
            self._write_text(self.api_dir / "export_error.txt", response.text)
            return
        content_type = response.headers.get("content-type", "")
        suffix = ".csv" if "csv" in content_type or response.text.startswith(",") or "text/" in content_type else ".json"
        path = self.artifact_dir / f"campaign_export{suffix}"
        if suffix == ".json":
            self._write_text(path, json.dumps(response.json(), indent=2, sort_keys=True) + "\n")
        else:
            self._write_bytes(path, response.content)

    def _write_final_report(self, active_space: dict[str, list[BuildingBlock]]) -> None:
        report = {
            "run_type": "successor_continuation",
            "predecessor_campaign_id": self.predecessor_campaign_id,
            "successor_campaign_id": self.successor_campaign_id,
            "predecessor_export": str(self.predecessor_export_path),
            "active_space_sizes": {
                "caps": len(active_space["caps"]),
                "bridges": len(active_space["bridges"]),
                "cores": len(active_space["cores"]),
            },
            "seeded_completed_results": len(self.seeded_results),
            "live_requested": self.args.total_live_evaluations,
            "live_attempted": self.live_attempted,
            "live_successful": len(self.live_successful_results),
            "live_failed": self.live_failed,
            "total_successor_results": len(self.all_successful_results),
            "duplicate_suggestions": self.duplicate_suggestions,
            "rejected_suggestions": self.rejected_suggestions,
            "pareto_candidates": self._pareto_count(self.all_successful_results),
            "artifact_dir": str(self.artifact_dir),
        }
        self._write_json(self.artifact_dir / "final_report.json", report)
        print(f"predecessor_campaign_id: {report['predecessor_campaign_id']}")
        print(f"successor_campaign_id: {report['successor_campaign_id']}")
        print(
            "active_space_sizes: "
            f"caps={report['active_space_sizes']['caps']}, "
            f"bridges={report['active_space_sizes']['bridges']}, "
            f"cores={report['active_space_sizes']['cores']}"
        )
        print(f"seeded_completed_results: {report['seeded_completed_results']}")
        print(f"live_attempted: {report['live_attempted']} / {report['live_requested']}")
        print(f"live_successful: {report['live_successful']}")
        print(f"live_failed: {report['live_failed']}")
        print(f"duplicate_suggestions: {report['duplicate_suggestions']}")
        print(f"pareto_candidates: {report['pareto_candidates']}")
        print(f"artifact_dir: {report['artifact_dir']}")

    @staticmethod
    def _pareto_count(results: list[dict[str, Any]]) -> int:
        objectives = [item["objective_values"] for item in results]
        count = 0
        for i, a in enumerate(objectives):
            dominated = False
            for j, b in enumerate(objectives):
                if i == j:
                    continue
                at_least_as_good = (
                    b["max_oscillator_strength_s1_s3"] >= a["max_oscillator_strength_s1_s3"]
                    and b["color_error_eV"] <= a["color_error_eV"]
                    and b["conformational_ambiguity"] <= a["conformational_ambiguity"]
                )
                strictly_better = (
                    b["max_oscillator_strength_s1_s3"] > a["max_oscillator_strength_s1_s3"]
                    or b["color_error_eV"] < a["color_error_eV"]
                    or b["conformational_ambiguity"] < a["conformational_ambiguity"]
                )
                if at_least_as_good and strictly_better:
                    dominated = True
                    break
            if not dominated:
                count += 1
        return count

    @staticmethod
    def _candidate_from_parameter_values(parameter_values: dict[str, Any]) -> Candidate:
        return Candidate(
            cap_id=str(parameter_values["cap_id"]),
            bridge_id=str(parameter_values["bridge_id"]),
            core_id=str(parameter_values["core_id"]),
        )

    @staticmethod
    def _candidate_in_active_space(candidate: Candidate, active_space: dict[str, list[BuildingBlock]]) -> bool:
        return (
            candidate.cap_id in {block.hid for block in active_space["caps"]}
            and candidate.bridge_id in {block.hid for block in active_space["bridges"]}
            and candidate.core_id in {block.hid for block in active_space["cores"]}
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        artifact_name: str,
    ) -> dict[str, Any]:
        response = requests.request(
            method=method.upper(),
            url=f"{self.api_base}{path}",
            headers=self._headers(extra_headers),
            json=json_body,
            params=params,
            timeout=self.args.request_timeout_s,
        )
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Non-JSON response from {path}: {response.text[:500]}") from exc
        self._write_json(self.api_dir / artifact_name, {"status_code": response.status_code, "body": data})
        if response.status_code >= 400:
            raise RuntimeError(f"BO API {path} failed with HTTP {response.status_code}: {data}")
        return data

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _idempotency_key(self, label: str) -> str:
        payload = f"{self.run_nonce}:{label}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Digital OSL BO/PySCF continuation campaign as a successor to a terminated predecessor.")
    parser.add_argument("--catalog-dir", default=".", help="Workspace directory containing product_smiles.py and adk9227_data_s1/s2/s3.csv")
    parser.add_argument("--campaign-name", default=None)
    parser.add_argument("--artifact-dir", default=None, help="Workspace-relative artifact directory. Default: timestamped artifacts/... directory")
    parser.add_argument("--predecessor-campaign-id", default=DEFAULT_PREDECESSOR_CAMPAIGN_ID)
    parser.add_argument("--predecessor-export", default=DEFAULT_PREDECESSOR_EXPORT)
    parser.add_argument("--expected-seed-count", type=int, default=6)
    parser.add_argument("--cap-limit", type=int, default=25)
    parser.add_argument("--bridge-limit", type=int, default=25)
    parser.add_argument("--core-limit", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--total-live-evaluations", type=int, default=10)
    parser.add_argument("--max-suggestion-rounds-per-batch", type=int, default=6)
    parser.add_argument("--e-target-ev", type=float, default=2.8)
    parser.add_argument("--num-conformers", type=int, default=6)
    parser.add_argument("--ambiguity-window-kcal", type=float, default=1.0)
    parser.add_argument("--rdkit-seed", type=int, default=7)
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--pyscf-timeout-s", type=int, default=900)
    parser.add_argument("--request-timeout-s", type=int, default=180)
    parser.add_argument("--synthetic-evaluator", action="store_true", help="Validation-only fast path that skips PySCF and emits synthetic finite objectives.")
    parser.add_argument("--terminate-on-exit", action="store_true", help="Terminate the successor BO campaign at the end of the run.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.batch_size != 2:
        raise SystemExit("This continuation script is written for BO batch size 2.")
    if args.total_live_evaluations <= 0:
        raise SystemExit("--total-live-evaluations must be positive.")
    if args.total_live_evaluations % args.batch_size != 0:
        raise SystemExit("--total-live-evaluations must be divisible by --batch-size so each BO round stays full-sized.")
    runner = CampaignRunner(args)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
