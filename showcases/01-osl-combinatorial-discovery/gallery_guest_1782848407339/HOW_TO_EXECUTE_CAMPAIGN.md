# How to execute the continuation BO/PySCF campaign

## What this run does

This workflow creates a **new successor BO-MCP campaign** for the terminated predecessor campaign:

- **Predecessor campaign_id:** `d661d8e6-34c2-476f-a065-4c485509e50f`
- **Predecessor export CSV:** `artifacts/run_20260630-195356/campaign_export.csv`

Because the predecessor was terminated on exit, this continuation script **does not attempt to resume it directly**. Instead it:

1. Rebuilds the same filtered active space from the three CSV catalogs.
2. Creates a fresh successor campaign with the same optimization setup.
3. Seeds the successor with the **6 completed historical results** from the predecessor export CSV.
4. Requests BO suggestions in **batches of 2**.
5. Runs **10 new live chemistry evaluations** total.
6. Submits only successful measurements to BO-MCP.
7. Marks failed or duplicate suggestions as **rejected** in BO-MCP rather than submitting fake measurements.

## Chemistry / evaluation policy preserved from the prior smoke test

The continuation script preserves the requested policy:

- Active space: keep the **25 smallest** fragments in each of the 3 catalogs by:
  1. RDKit heavy-atom count
  2. total atom count
  3. SMILES length
- Product generation: **only** through `product_smiles.py` / `DigitalOslProductSmiles`
- Conformers: RDKit **ETKDG + MMFF**, then choose the lowest-energy conformer
- PySCF workflow: **RKS PBE/3-21G single point only**
- No geometry optimization
- No frequencies
- Excited states: **TDA-TDDFT first 3 singlet states**
- Successful BO submission requires:
  - single-point energy
  - TDDFT singlet energies + oscillator strengths
  - molecular-analysis output
- Objectives:
  - maximize `max_oscillator_strength_s1_s3`
  - minimize `color_error_eV` relative to `E_target = 2.8 eV` by default
  - minimize `conformational_ambiguity`

## Files

- **Driver script:** `smallest_fragments_digital_osl_bo_continuation.py`
- **This guide:** `HOW_TO_EXECUTE_CAMPAIGN.md`

## Required environment

At minimum, the script requires:

- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

Recommended to keep the default graph/PySCF-related environment consistent with the container setup:

- `GRAPHCHAT_AGENT_WS_URL` or `VITE_WS_URL`
- `GRAPHCHAT_ROOM`
- `SPARQL_ENDPOINT`

The script fails fast if `BO_MCP_API_KEY` is missing.

## Recommended execution pattern

Run from the shared workspace directory containing:

- `smallest_fragments_digital_osl_bo_continuation.py`
- `product_smiles.py`
- `adk9227_data_s1.csv`
- `adk9227_data_s2.csv`
- `adk9227_data_s3.csv`
- `artifacts/run_20260630-195356/campaign_export.csv`

Recommended shell pattern:

```bash
set -o pipefail
RUN_TS="$(date +%Y%m%d-%H%M%S)"
LOG_PATH="artifacts/continuation_run_${RUN_TS}.log"
mkdir -p artifacts

PYTHONUNBUFFERED=1 uv run python -u smallest_fragments_digital_osl_bo_continuation.py \
  --artifact-dir "artifacts/continuation_run_${RUN_TS}" \
  2>&1 | tee "${LOG_PATH}"

exit ${PIPESTATUS[0]}
```

That pattern gives you:

- **unbuffered Python output** for live monitoring
- a **timestamped workspace log file**
- **true process exit status** preserved even though output is piped through `tee`

## Optional flags

### Keep the default continuation settings

Defaults already match the requested follow-up:

- `--batch-size 2`
- `--total-live-evaluations 10`
- `--expected-seed-count 6`
- predecessor campaign/export defaults are already prefilled

So the simplest real run is just:

```bash
PYTHONUNBUFFERED=1 uv run python -u smallest_fragments_digital_osl_bo_continuation.py
```

### Useful overrides

```bash
--campaign-name "custom-successor-name"
--artifact-dir "artifacts/my_successor_run"
--e-target-ev 2.8
--pyscf-timeout-s 900
--terminate-on-exit
```

Notes:

- `--terminate-on-exit` is **optional**. By default, the successor campaign is left available after the run.
- The script is intentionally fixed to **batch size 2**.
- `--total-live-evaluations` must stay divisible by 2 so every BO round remains full-sized.

## Expected runtime behavior

High-level stdout is intentionally compact. You should see messages like:

- successor seeding summary
- one line per continuation batch
- final report including predecessor and successor campaign IDs

The script writes detailed artifacts under the selected artifact directory, including:

- `campaign_intake.json`
- `active_space.json`
- `active_space_caps.csv`
- `active_space_bridges.csv`
- `active_space_cores.csv`
- `seed_rows.json`
- `campaign_export.csv` (or `.json` if the API returns JSON)
- `final_report.json`
- `api/` request/response captures
- `evaluations/` per-candidate artifacts:
  - `product.smiles`
  - `conformers.json`
  - `selected_conformer.xyz`
  - `selected_conformer.sdf`
  - `pyscf_result.json`
  - `result.json` or `failure.json`

## Validation / success checks

After completion, check:

1. `final_report.json`
2. the printed `successor_campaign_id`
3. `campaign_export.csv`
4. per-candidate folders under `evaluations/`

Key fields to verify in `final_report.json`:

- `predecessor_campaign_id`
- `successor_campaign_id`
- `seeded_completed_results` should be `6`
- `live_attempted` should be `10`
- `active_space_sizes` should be `25 / 25 / 25`

If all live evaluations succeed, then:

- `live_successful` should be `10`
- `live_failed` should be `0`
- `total_successor_results` should be `16`

## Important caveats

### 1) The predecessor campaign is not resumable

The predecessor was terminated on exit, so the correct continuation behavior is to create a **new successor campaign** and seed from the export CSV. Do **not** expect the old campaign to accept new suggestions/results.

### 2) Seed rows must remain inside the reconstructed active space

The script intentionally rebuilds the filtered 25/25/25 active space and checks that the 6 historical seed tuples are still inside it. If they are not, the run aborts rather than silently changing campaign semantics.

### 3) Duplicate BO suggestions are handled defensively

The script avoids re-evaluating seeded or already-attempted tuples. If BO-MCP still returns a duplicate suggestion, the script rejects that suggestion in BO-MCP and asks for replacement suggestions.

### 4) Failed chemistry evaluations are not submitted as successful measurements

If a candidate fails during product generation, conformer generation, or PySCF extraction, the script records local failure artifacts and marks the BO suggestion as rejected.

### 5) PySCF runs can still be slow

Each live batch contains 2 candidates and the script evaluates them in parallel. Even with that, real PySCF wall time may still be substantial.
