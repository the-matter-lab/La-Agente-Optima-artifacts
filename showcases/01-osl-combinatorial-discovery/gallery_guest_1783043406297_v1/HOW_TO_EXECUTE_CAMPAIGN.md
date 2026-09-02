# Stage 1b Digital OSL Campaign: review and execution guide

## What this campaign is

This workspace now contains a **new Stage 1b BO-MCP + PySCF campaign** for digital organic solid-state laser discovery over fragment-assembled `A-B-C-B-A` molecules.

Entrypoint:

```bash
uv run python run_digital_osl_stage1b.py
```

Default behavior is **safe preview / preflight only**. It prepares the expanded search space, BO intake, and legacy-import plan, then stops before campaign creation.

## Scientific compatibility with the earlier Stage 1 campaign

Stage 1b keeps the prior scientific setup so the old successful observations remain reusable:

- same objectives:
  - `bright_osc_strength` — maximize
  - `color_error_ev` — minimize
  - `ambiguity_penalty` — minimize
- same cheap evaluator:
  - CREST conformer search with **GFN-FF**
  - PySCF **PBE / def2-SVP**
  - **no geometry optimization**
  - **no frequency calculation**
- same fragment assembly rule and same `A-B-C-B-A` construction logic
- same BO style by default: **BO-MCP + BayBE custom categorical parameters**

## Legacy Stage 1 results reused in Stage 1b

Legacy source:

- prior campaign id: `03cd5601-f16d-4e76-a588-7d15bf8268cb`
- import file used by default: `artifacts/digital_osl_stage1/20260703T031540Z_execute/campaign_export.csv`

Stage 1b imports the **16 successful Stage 1 observations** from that export, provided they are inside the new Stage 1b space.

Because Stage 1b is constructed as a strict superset of the original Stage 1 active fragment sets, the import plan includes **all 16 / 16** legacy successes.

Imported candidate ids:

- `A014B065C069`
- `A031B065C025`
- `A014B056C025`
- `A031B056C069`
- `A014B066C115`
- `A014B056C100`
- `A014B056C080`
- `A014B056C115`
- `A014B065C078`
- `A014B056C070`
- `A014B065C070`
- `A014B065C025`
- `A014B065C041`
- `A014B065C036`
- `A031B065C041`
- `A031B065C069`

## How the new Stage 1b search space is built

### Superset guarantee

The whole original Stage 1 active space is retained as a subset.

Original Stage 1 active fragment ids:

- caps: `A014 A042 A041 A031 A015 A039`
- bridges: `B065 B066 B067 B056 B057 B037`
- cores: `C069 C094 C115 C025 C070 C078 C100 C080 C036 C041`

Stage 1b starts from those exact ids and only **adds** fragments.

That guarantees the original `6 x 6 x 10 = 360` candidate space is fully included in the new Stage 1b campaign.

### Deterministic frontier-aware expansion rule

The expansion is deterministic and reviewable:

1. Read the 16 successful Stage 1 observations from the legacy export CSV.
2. Compute the observed Pareto frontier using:
   - maximize `bright_osc_strength`
   - minimize `color_error_ev`
   - minimize `ambiguity_penalty`
3. For each fragment slot independently, collect the fragment ids that appear on that legacy frontier.
4. Keep **all** original Stage 1 active ids.
5. For each remaining feasible fragment outside the old active set, compute its minimum z-scored custom-descriptor distance to the frontier fragment anchors in the same slot.
6. Rank additions by:
   1. smaller minimum descriptor distance to the frontier anchor set,
   2. smaller heavy-atom count,
   3. smaller exact molecular weight,
   4. smaller rotatable-bond count,
   5. identifier order.
7. Add the top-ranked new fragments until the target counts are reached.

Legacy frontier fragment anchors used by the default Stage 1b build:

- cap anchors: `A014`, `A031`
- bridge anchors: `B056`, `B065`
- core anchors: `C025`, `C036`, `C041`, `C069`, `C070`, `C078`, `C100`

## Default Stage 1b active fragment sets

Default target counts:

- `--cap-target 12`
- `--bridge-target 12`
- `--core-target 18`

This yields **2592 candidates** total.

### Caps (12)

Original 6 retained:

- `A014`, `A042`, `A041`, `A031`, `A015`, `A039`

Added 6 frontier-near caps:

- `A032`, `A004`, `A020`, `A025`, `A001`, `A008`

### Bridges (12)

Original 6 retained:

- `B065`, `B066`, `B067`, `B056`, `B057`, `B037`

Added 6 frontier-near bridges:

- `B049`, `B046`, `B048`, `B062`, `B043`, `B032`

### Cores (18)

Original 10 retained:

- `C069`, `C094`, `C115`, `C025`, `C070`, `C078`, `C100`, `C080`, `C036`, `C041`

Added 8 frontier-near cores:

- `C098`, `C125`, `C018`, `C071`, `C117`, `C023`, `C107`, `C031`

## Execution modes

## 1) Safe preview / preflight mode

Default command:

```bash
uv run python run_digital_osl_stage1b.py
```

This will:

- validate the assembly rule against `adk9227_data_s6.csv`
- build the deterministic Stage 1b superset search space
- prepare the BO campaign intake
- prepare the legacy import plan
- optionally call BO-MCP `validate_intake`
- **not** create a campaign
- **not** import old results
- **not** run BO suggestions
- **not** run chemistry evaluations

Optional review examples:

```bash
uv run python run_digital_osl_stage1b.py --skip-bo-validate
uv run python run_digital_osl_stage1b.py --cap-target 12 --bridge-target 12 --core-target 18
```

## 2) Real Stage 1b run for 30 BO iterations beyond import

Use this after reviewing the preview artifacts:

```bash
uv run python run_digital_osl_stage1b.py --execute
```

The default execution settings already target:

- import the 16 legacy successful Stage 1 observations first
- then run up to `--max-new-bo-successes 30`
- with `batch_size=1`, that means **30 new BO suggestions/evaluations beyond the imported history**
- pause the campaign at invocation end unless `--terminate-on-exit` is explicitly supplied

Explicit recommended command:

```bash
uv run python run_digital_osl_stage1b.py \
  --execute \
  --cap-target 12 \
  --bridge-target 12 \
  --core-target 18 \
  --max-new-bo-successes 30 \
  --max-runtime-minutes 1440 \
  --target-energy-ev 2.65 \
  --low-state-window 5 \
  --tddft-nstates 6 \
  --basis-set def2-SVP \
  --xc-functional PBE \
  --crest-method gfnff \
  --pyscf-timeout-s 900 \
  --evaluation-timeout-s 1200
```

## 3) Continuation / resumption

If the Stage 1b campaign already exists, resume the same campaign with:

```bash
uv run python run_digital_osl_stage1b.py --execute --campaign-id <STAGE1B_CAMPAIGN_ID>
```

Lifecycle behavior encoded in the script:

- paused campaign -> `resume`
- completed campaign -> `reopen`
- existing campaign is **not rebuilt**
- invocation ends with **pause** by default
- use `--terminate-on-exit` only when you explicitly want to close the campaign

The script also checks for already-present results in the attached Stage 1b campaign, so resuming does not re-import or re-submit candidates that are already there.

## 4) BO-loop smoke test

This is for engineering validation only:

```bash
uv run python run_digital_osl_stage1b.py \
  --execute \
  --evaluation-backend synthetic \
  --max-new-bo-successes 1 \
  --terminate-on-exit
```

## Environment requirements

Required for BO execution / BO validation:

- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

Required for direct CREST + PySCF execution through the repository tools:

- `GRAPHCHAT_AGENT_WS_URL` or `VITE_WS_URL` (default fallback: `ws://graphchat:3000`)
- `GRAPHCHAT_ROOM` (default fallback: `room`)
- `SPARQL_ENDPOINT` (default fallback: `http://blazegraph:8080/blazegraph/namespace/kb/sparql`)

Assumed tooling:

- `uv`
- repository Python environment already available in the container
- CREST / xtb stack available
- PySCF workflow support available

## Expected artifacts

Artifacts are written under:

- `artifacts/digital_osl_stage1b/<run_label>/`

Preview artifacts include:

- `run_config.json`
- `assembly_validation.json`
- `active_caps.csv`
- `active_bridges.csv`
- `active_cores.csv`
- `candidate_library.csv`
- `legacy_import_plan.json`
- `legacy_import_rows.csv`
- `campaign_intake.json`
- `preview_summary.json`
- `validate_intake_response.json` (when BO validation runs)
- `PREVIEW.txt`

Execution artifacts additionally include:

- `campaign_create_response.json` or `attached_campaign.json`
- `campaign_runtime.json`
- `legacy_import_runtime.json`
- `legacy_import_submissions.jsonl`
- `suggestions.jsonl`
- `results_success.jsonl`
- `results_failures.jsonl`
- `diagnostics_history.jsonl`
- `loop_decisions.jsonl`
- `campaign_export.csv`
- `campaign_export_meta.json`
- `final_campaign_state.json`
- `lifecycle_on_exit.json` (when a lifecycle action is taken)

## Final notes

- Stage 1b is designed to be a **strict superset** of the original Stage 1 active fragment sets.
- Old Stage 1 successes are reused by import, not recomputation.
- The execution loop uses BO-MCP as the campaign state authority.
- Preview mode is the safe default.
