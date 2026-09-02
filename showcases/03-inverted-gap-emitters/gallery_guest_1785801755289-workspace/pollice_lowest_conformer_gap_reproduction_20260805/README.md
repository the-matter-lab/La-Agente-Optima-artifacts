# Pollice 2021 lowest-conformer TD-DFT BO campaign reproduction bundle

This folder contains the campaign inputs, configuration, code, results, logs, and plotting script for documenting/reproducing the BO campaign.

## Campaign snapshot

- Campaign ID: `f023cf90-a1a1-470a-987d-134a38919812`
- Status at export: `paused`
- Candidate CSV: `input/pollice_2021_geometry_available.csv`
- Filter: RDKit heavy atoms `< 56` (1512 candidates)
- BO backend: BayBE through BO-MCP
- Objective: maximize `negative_singlet_triplet_gap = -(S1_ev - T1_ev)`
- Evaluation protocol: CREST/GFN2-xTB conformer generation from `smiles_canonical`, lowest-energy generated conformer only, restricted closed-shell PBE0/def2-SVP gas-phase TD-DFT.
- Charge/multiplicity: 0 / singlet 1
- Batch size: 2
- Initial design size: 5
- Per-evaluation timeout used: 7200 s

## Current results at export

- Attempted evaluations: 44
- Successful evaluations: 39
- Failed evaluations: 5

Best molecule:

- `molecule_key`: `WGKMZGAJDYWUCE-UHFFFAOYSA-N`
- `smiles_canonical`: `CS(=O)C1=CC=C2C=CC=C3C=CC=C1N32`
- `delta_est_ev`: 0.223230819959 eV
- `objective`: -0.223230819959
- `S1_ev`: 1.39801950296 eV
- `T1_ev`: 1.174788683 eV
- `oscillator_strength`: 0.000233881249702
- `n_conformers_generated`: 4

## Folder contents

- `input/` — original campaign CSV used as the molecule pool.
- `data/`
  - `evaluation_results.csv` — one row per attempted evaluation.
  - `evaluation_results.jsonl` — append-only provenance records.
  - `bo_export.csv` — BO-MCP campaign export.
  - `campaign_intake.json` — exact BO-MCP intake payload.
  - `campaign_manifest.json`, `HOW_TO_EXECUTE_CAMPAIGN.md` — campaign package metadata/instructions.
  - `top10_ranked_results.csv` — top 10 successful rows ranked by objective.
- `code/` — campaign entry point and Python package used to run the campaign.
- `scripts/plot_bo_improvement.py` — standalone plot regeneration script.
- `plots/`
  - `bo_improvement_curve.png`
  - `bo_improvement_curve.pdf`
  - `bo_improvement_curve_data.csv`
- `logs/` — monitor logs from the production run and continuations.
- `metadata/` — environment and summary metadata.

## Regenerate the plot

From this folder:

```bash
python scripts/plot_bo_improvement.py
```

This reads `data/evaluation_results.csv` and writes the plot files under `plots/`.

## Continue the live campaign

This folder is a documentation/reproduction bundle. To continue the live BO-MCP campaign in the original workspace, use campaign ID:

```text
f023cf90-a1a1-470a-987d-134a38919812
```

See `data/HOW_TO_EXECUTE_CAMPAIGN.md` for the command pattern. The campaign was paused at export.
