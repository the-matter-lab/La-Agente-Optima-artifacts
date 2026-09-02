from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

from grafico.deps import GraficoDeps
from domains.crest.crest_tools import run_crest_conformer_search
from domains.pyscf.tools.pyscf_workflow_tools import run_pyscf_workflow

HARTREE_TO_EV = 27.211386245988
TARGET_EV = 2.65
LOW_STATE_WINDOW = 5

CANDIDATES = {
    'A014B056C078': 'CN(C)c1ccc(-c2ccc(-c3csc(-c4ccc(-c5ccc(N(C)C)cc5)s4)n3)s2)cc1',
    'A015B065C036': 'CN(C)c1ccc(C=Cc2cccc(C=Cc3ccc(N(C)C)c4ccccc34)c2)c2ccccc12',
    'A014B065C036': 'CN(C)c1ccc(C=Cc2cccc(C=Cc3ccc(N(C)C)cc3)c2)cc1',
    'A014B065C041': 'CN(C)c1ccc(C=Cc2cccc(C=Cc3ccc(N(C)C)cc3)n2)cc1',
}


def make_ctx():
    return SimpleNamespace(
        deps=GraficoDeps(
            ws_url=os.getenv('GRAPHCHAT_AGENT_WS_URL') or os.getenv('VITE_WS_URL', 'ws://graphchat:3000'),
            room=os.getenv('GRAPHCHAT_ROOM', 'room'),
            sparql_endpoint=os.getenv('SPARQL_ENDPOINT', 'http://blazegraph:8080/blazegraph/namespace/kb/sparql'),
        )
    )


def pick_bright_state(result):
    if hasattr(result, 'tddft_results'):
        tr = result.tddft_results
    else:
        tr = result['tddft_results']
    sing_e = tr['tddft_singlet_energies']
    sing_f = tr['tddft_singlet_oscillator_strength']
    n = min(LOW_STATE_WINDOW, len(sing_e), len(sing_f))
    pairs = [(i + 1, sing_e[i] * HARTREE_TO_EV, sing_f[i]) for i in range(n)]
    bright_idx, bright_ev, bright_f = max(pairs, key=lambda x: x[2])
    return {
        'low_states_window': pairs,
        'bright_state_index_1based': bright_idx,
        'bright_state_energy_ev': bright_ev,
        'bright_state_oscillator_strength': bright_f,
        'color_error_ev': abs(bright_ev - TARGET_EV),
    }


def main():
    os.environ.setdefault('LOGFIRE_IGNORE_NO_CONFIG', '1')
    outdir = Path('artifacts/confirm_wb97xd4_four')
    outdir.mkdir(parents=True, exist_ok=True)
    ctx = make_ctx()
    summary = []
    for cid, smiles in CANDIDATES.items():
        print(f'=== {cid}: CREST/GFN2-xTB ===', flush=True)
        crest = run_crest_conformer_search(
            ctx,
            smiles,
            'smiles',
            charge=0,
            spin_multiplicity=1,
            calculation_level_method='gfn2',
            crest_runtype='imtd-gc',
            run_on_gpu=False,
            threads=8,
        )
        best = min(crest, key=lambda r: (r['erel_kcal'], r['index']))

        print(f'=== {cid}: wB97X-D4/def2-SVP geometry optimization ===', flush=True)
        geom = run_pyscf_workflow(
            ctx,
            'Optimize the geometry of this conformer with DFT. Skip frequency analysis and stop after geometry optimization.',
            'conceptual_atoms_iri',
            best['conceptual_atoms_iri'],
            charge=0,
            spin_multiplicity=1,
            basis_set='def2-SVP',
            restricted=True,
            xc_functional='wB97X-D4',
            exit_node='GeometryOptimisation',
            update_graph=False,
            geometry_max_steps=100,
            workflow_timeout_s=3600,
        )

        print(f'=== {cid}: wB97X-D4/def2-TZVP excited states on optimized geometry ===', flush=True)
        excit = run_pyscf_workflow(
            ctx,
            'Compute low-lying singlet excited states for this already optimized geometry. Do not re-optimize and skip frequency analysis.',
            'xyz',
            geom.final_molecule.identifier,
            charge=0,
            spin_multiplicity=1,
            basis_set='def2-TZVP',
            restricted=True,
            xc_functional='wB97X-D4',
            exit_node='TDDFT',
            update_graph=False,
            tddft_nstates=10,
            workflow_timeout_s=3600,
        )

        bright = pick_bright_state(excit)
        row = {
            'candidate_id': cid,
            'smiles': smiles,
            'crest_best_conformer_iri': best['conceptual_atoms_iri'],
            'crest_best_erel_kcal': best['erel_kcal'],
            'crest_best_weight': best['weight'],
            'geom_total_energy_hartree': geom.total_energy,
            'geom_final_molecule_iri': geom.final_molecule.instance_iri,
            'excited_total_energy_hartree': excit.total_energy,
            'xc_functional': excit.xc_functional,
            'geom_basis_set': geom.basis_set,
            'excited_basis_set': excit.basis_set,
            **bright,
            'excitation_result': excit.model_dump(),
        }
        summary.append(row)
        (outdir / f'{cid}.json').write_text(json.dumps(row, indent=2))

    csv_path = outdir / 'summary.csv'
    with csv_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            'candidate_id', 'crest_best_erel_kcal', 'crest_best_weight',
            'geom_total_energy_hartree', 'excited_total_energy_hartree',
            'bright_state_index_1based', 'bright_state_energy_ev',
            'bright_state_oscillator_strength', 'color_error_ev'
        ])
        for r in summary:
            w.writerow([
                r['candidate_id'], r['crest_best_erel_kcal'], r['crest_best_weight'],
                r['geom_total_energy_hartree'], r['excited_total_energy_hartree'],
                r['bright_state_index_1based'], r['bright_state_energy_ev'],
                r['bright_state_oscillator_strength'], r['color_error_ev']
            ])
    print(f'Wrote {csv_path}', flush=True)


if __name__ == '__main__':
    main()
