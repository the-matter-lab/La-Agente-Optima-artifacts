# Hood-inspired cationic Co(II) bisphosphine BO campaign

## Files

- Entry point: `run_hood_co_bisphosphine_bo.py`
- Package: `hood_co_bisphosphine_bo/`
- Manifest: `campaign_manifest.json`
- Default artifacts directory: `hood_co_bisphosphine_artifacts/`

## What the script does before any calculation

Every invocation first constructs the full finite ligand library and writes:

- `hood_co_bisphosphine_artifacts/candidate_library.json`
- `hood_co_bisphosphine_artifacts/candidate_library.csv`

It prints an `[EVENT]` line reporting:

- total candidates = 144
- candidates per linker = 36 for each of ethylene, propylene, 1,2-phenylene, cis-1,2-cyclohexylene
- symmetric `R1=R2` candidates = 32
- unsymmetric `R1!=R2` candidates = 112
- duplicate candidate ids = 0
- duplicate unordered `R1/R2` permutations remaining = 0

The ligand library is `R1_2P-linker-PR2_2`, where `R1/R2` are unordered pairs with repetition from `Me, Et, iPr, Cy, Ph, p-Tol, p-Anisyl, p-CF3-Ph`. Definitions used in prompts: `p-Tol = 4-methylphenyl`, `p-Anisyl = 4-methoxyphenyl`, `p-CF3-Ph = 4-trifluoromethylphenyl`.

## Safety modes and whether calculations start

Default behavior is safe: if no execution flag is supplied, the script reports the library and exits. It does **not** create BO suggestions, call Estructural, or run PySCF.

Library-only dry run:

```bash
uv run python run_hood_co_bisphosphine_bo.py --library-only
```

Create/validate BO campaign only, with no suggestions or calculations:

```bash
uv run python run_hood_co_bisphosphine_bo.py --create-only
```

Smoke-test one BO iteration without chemistry calculations:

```bash
uv run python run_hood_co_bisphosphine_bo.py \
  --mock-evaluator \
  --max-successes 1 \
  --poll-s 0 \
  --terminate-on-exit
```

Warm-start preset requested for production: exactly four documented warm-start evaluations followed by ten BO-selected evaluations:

```bash
uv run python run_hood_co_bisphosphine_bo.py \
  --hood-warm-start-bo10 \
  --run-calculations
```

Before creating a campaign or submitting any production evaluation, this mode performs three preflights: (1) socket connectivity to `ESTRUCTURAL_A2A_URL`, (2) a trivial water XYZ write/read round trip in the current workspace context, and (3) a tiny PySCF literal-XYZ handoff check using that Estructural-produced XYZ. Do not override `ESTRUCTURAL_A2A_URL` to `http://estructural:8000` in this Docker network; that host may not resolve. Use the default `http://a2a:8033` or explicitly set it. Also ensure `GRAPHCHAT_ROOM`, if set, matches this workspace; if it is unset, the script falls back to the current workspace directory name.

```bash
ESTRUCTURAL_A2A_URL=http://a2a:8033 \
uv run python -u run_hood_co_bisphosphine_bo.py \
  --hood-warm-start-bo10 \
  --run-calculations
```

If preflight fails, the script prints `[ALERT]` and exits before campaign creation/evaluation submission, so infrastructure, workspace-context, or PySCF handoff failures are not converted into penalized fake chemistry failures. During candidate evaluation, an Estructural response that does not create a parseable XYZ file, or a PySCF file/path handoff failure, is also treated as non-submittable infrastructure/output failure; it is not submitted to BO-MCP as a hard-penalty chemistry observation. The evaluator passes XYZ **literal content** to PySCF (`identifier_type="xyz"`) rather than a relative `xyz_filename`, avoiding PySCF's internal `/app/evals/pyscf/xyz_files` path resolution.

The four warm-start candidate IDs are chemically diverse across linkers, steric profiles, and electronics:

1. `eth__Me__Me` — ethylene linker, smallest symmetric alkyl substituents.
2. `prop__iPr__Ph` — propylene linker, unsymmetric alkyl/aryl substituents.
3. `ophen__pAnisyl__pCF3Ph` — rigid 1,2-phenylene linker with electron-rich/electron-poor aryl contrast.
4. `cchex__Cy__pTol` — cis-1,2-cyclohexylene linker with bulky cycloalkyl/aryl substituents.

With `--hood-warm-start-bo10`, the script first evaluates and submits exactly these four warm-start candidates as completed BO-MCP observations, then requests BO-MCP/BayBE suggestions for ten additional BO-selected iterations. Warm-start evaluations are counted separately from BO-selected iterations: `4 warm_start + 10 bo = 14 total evaluations` for a fresh production run. The warm-start list is also written to `hood_co_bisphosphine_artifacts/warm_start_candidates.json`.

Mock-only bounded test of the warm-start workflow, with only one BO-selected suggestion after the four mock warm starts:

```bash
uv run python run_hood_co_bisphosphine_bo.py \
  --hood-warm-start-bo10 \
  --mock-evaluator \
  --bo-iterations 1 \
  --poll-s 0 \
  --terminate-on-exit
```

`--bo-iterations` overrides the post-warm-start BO count and is intended for bounded smoke tests; omit it in production to use the preset value of 10.

Production calculation mode, one selected candidate this invocation:

```bash
uv run python run_hood_co_bisphosphine_bo.py \
  --run-calculations \
  --max-successes 1
```

Resume a paused/completed campaign:

```bash
uv run python run_hood_co_bisphosphine_bo.py \
  --campaign-id <CAMPAIGN_ID> \
  --run-calculations \
  --max-successes 1
```

Recommended fresh campaign after the convergence/electronic-parser update:

```bash
rm -f STOP
unset GRAPHCHAT_ROOM
ESTRUCTURAL_A2A_URL=http://a2a:8033 \
uv run python -u run_hood_co_bisphosphine_bo.py \
  --hood-warm-start-bo10 \
  --run-calculations \
  --campaign-name hood-co-bisphosphine-cationic-coii-pbe-converged \
  --artifacts-dir hood_co_bisphosphine_artifacts_pbe_converged
```

If you intentionally accept mixed objective definitions and want to continue the paused campaign `9f89066d-ee9e-4791-9491-a446a82cd3ea`, use:

```bash
ESTRUCTURAL_A2A_URL=http://a2a:8033 \
uv run python -u run_hood_co_bisphosphine_bo.py \
  --campaign-id 9f89066d-ee9e-4791-9491-a446a82cd3ea \
  --run-calculations \
  --max-successes 1 \
  --artifacts-dir hood_co_bisphosphine_artifacts_restart3
```


## Environment requirements

The active `uv` environment must provide:

- BO-MCP client and API access: `BO_MCP_API_URL`, `BO_MCP_API_KEY`
- Estructural A2A service access for production calculations: `ESTRUCTURAL_A2A_URL` or its default in-network endpoint
- Workspace/room context: `GRAPHCHAT_ROOM` is used as Estructural `context_id`
- PySCF workflow dependencies available in the repository environment

## Computational assumptions

The production evaluator builds precursor-like cationic complexes `[Co(acac)(P2)]+` with Estructural and evaluates them with the repository PySCF workflow. Defaults are intentionally more generous after direct convergence testing on the smallest candidate:

- charge: `+1` (`--charge 1`)
- Co(II) spin multiplicity: doublet (`--spin-multiplicity 2`)
- DFT functional: `pbe` (`--xc-functional pbe`)
- basis set: `def2-svp` (`--basis-set def2-svp`)
- geometry optimization max steps: `200` (`--geometry-max-steps 200`)
- per-candidate PySCF workflow timeout: `7200 s` (`--workflow-timeout-s 7200`)

The script requests unrestricted DFT geometry optimization to actual convergence followed by molecular/electronic analysis. It explicitly does **not** request transition states, frequency calculations, TDDFT, full catalytic-cycle calculations, or energy-span calculations. XYZ is passed to PySCF as literal content rather than a relative filename.

## Objectives and feasibility handling

BO-MCP is configured with BayBE over one finite categorical parameter, `candidate_id`, using custom descriptor vectors for the candidate library and Pareto multi-objective optimization.

Objectives:

1. `electronic_activation` — maximize. Uses parsed PySCF electronic descriptors: preferred source is the chkfile (spin-resolved frontier orbitals, Mulliken charge, and Mulliken spin population at Co); `analysis_results` arrays are fallback. For unrestricted doublets, the alpha SOMO is used when `nalpha > nbeta`. The evaluation record stores Hartree/eV frontier energies and score components/provenance.
2. `coordination_stability` — maximize. Rewards successful optimization, both Co-P distances in a chemically reasonable range, low Co-P asymmetry, acac O,O coordination, and no ligand dissociation.
3. `chelate_geometry` — maximize. Rewards reasonable P-Co-P bite angle and limited square-planar distortion.
4. `steric_crowding` — minimize. Penalizes heavy atoms close to Co, low nonbonded distances, and bulky substituents that distort the coordination region.

Failed SCF, failed or unconverged geometry optimization, ligand/acac dissociation, unrealistic Co-P/Co-O distances, severe collapse, or infeasible geometry receive finite heavy penalties before submission to BO-MCP. Geometry optimization is marked successful only when `workflow_summary` contains `Geometry optimization completed` and does not contain failure indicators such as `Error in geometry optimization`, `Nuclear gradients`, `not converged`, timeout, or traceback/exception text; total energy alone is not sufficient.

## Runtime output tags

The entry point prints concise monitor-friendly tagged stdout lines:

- `[EVENT]` state changes, library reports, campaign create/resume/pause/export
- `[RESULT]` one-line per-experiment objective summary
- `[ALERT]` recoverable failures or rejected suggestions
- `[HEARTBEAT]` liveness during long invocations

Detailed per-candidate provenance is written to artifacts, not dumped to stdout.

## Artifacts

Default artifact paths:

- `hood_co_bisphosphine_artifacts/candidate_library.json`
- `hood_co_bisphosphine_artifacts/candidate_library.csv`
- `hood_co_bisphosphine_artifacts/campaign_id.txt`
- `hood_co_bisphosphine_artifacts/warm_start_candidates.json` when `--hood-warm-start-bo10` is used
- `hood_co_bisphosphine_artifacts/evaluations.jsonl`
- `hood_co_bisphosphine_artifacts/<candidate_id>/evaluation.json`
- `hood_co_bisphosphine_artifacts/<candidate_id>/<candidate_id>.xyz` for Estructural-generated structures in production mode
- `hood_co_bisphosphine_artifacts/estructural_preflight_response.json` and `estructural_preflight_<pid>.xyz` after production preflight
- `hood_co_bisphosphine_artifacts/pyscf_literal_preflight_result.json` and optional console log after production preflight
- `hood_co_bisphosphine_artifacts/<candidate_id>/estructural_response.json` and `.txt` for Estructural task output provenance
- `hood_co_bisphosphine_artifacts/campaign_export.csv`

## Stop file

Default stop file: `STOP` in the current working directory.

The script checks for this file before warm-start evaluations, immediately after the warm-start phase before any BO suggestion request, and at the top of each BO loop before requesting a suggestion. If present, it prints `[EVENT]`, deletes the file to avoid a stale stop on resume, and exits through normal shutdown. It does not check the stop file between evaluation and BO-MCP result submission, so completed evaluations are submitted before pausing/exiting.

## Notes

- Use `--max-successes` as the generic per-invocation BO-selected budget. With `--hood-warm-start-bo10`, omit `--bo-iterations` for the requested ten BO-selected iterations; `--bo-iterations` is an override for bounded smoke tests.
- The script pauses a running campaign at the end of a normal invocation. Use `--campaign-id` to continue later.
- `--terminate-on-exit` is intended for bounded smoke tests, not production campaigns.
- Do not continue campaign `0030e8d9-f737-49e8-a7dd-0bc3c89c146e`; it contains five submitted infrastructure-failure penalty observations from an invalid Estructural endpoint (`http://estructural:8000`). Do not continue campaign `90bb2180-9aaa-40cd-832d-a26137d410a7`; it contains two submitted Estructural workspace-output failure penalty observations from the previous context/path handling bug. Do not continue campaign `e446f8a5-02f4-4e4c-ac02-48eb95c904ee`; it contains two submitted PySCF path-resolution infrastructure penalty observations from the previous `xyz_filename` handoff bug. Start a fresh campaign after all preflights succeed.
- Campaign `9f89066d-ee9e-4791-9491-a446a82cd3ea` is a technically valid paused campaign, but it used older B3LYP/60-step settings and an older electronic objective parser that often submitted `electronic_activation=0` when analysis was missing. Prefer starting a fresh campaign for internally consistent PBE/def2-SVP, converged-geometry, chkfile-parsed objective values. If you continue `9f89066d-ee9e-4791-9491-a446a82cd3ea`, treat it as a mixed-objective-definition campaign.
