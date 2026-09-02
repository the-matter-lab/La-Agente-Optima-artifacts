# Yield-only RoboChemFlex BO-MCP campaign handoff

This package prepares a **new BO-MCP campaign** whose only objective is `yield_percent` maximized over `[0, 100]`. It reuses the existing RoboChemFlex search-space and RoboFlex request mapping. The previous `green_score` objective is removed from the BO objective list and scalarization is omitted. Green score is retained only as audit metadata/artifacts.

## Safety gates

- No command below starts hardware unless it includes both `--execute` and `--confirm-autonomous-hardware` on `continue_robochemflex_yield_only_bo.py`.
- The recreation command defaults to dry-run. BO-MCP campaign creation/seeding requires both `--execute-create-seed` and `--confirm-create-seed`.
- RoboFlex campaign creation is never performed by these scripts. Continuation submits runs only to the already-active campaign `robochemflex_yield_bo_fresh_20260724T155503Z-20260724-175502` after read checks confirm it is idle/awaiting_run.
- The main agent should ask the user again before running either the BO create/seed command or the later hardware continuation command.

## Files

- Package: `robochemflex_yield_only_bo/`
- Recreate/seed entrypoint: `recreate_robochemflex_yield_only_bo.py`
- Later continuation entrypoint: `continue_robochemflex_yield_only_bo.py`
- Manifest: `campaign_manifest_yield_only.json`

## 1. Dry-run/preflight only (safe now)

Writes a yield-only intake, the 20 historical seed rows, and an audit copy of the source export. This performs no BO mutation and no RoboFlex mutation.

```bash
uv run python recreate_robochemflex_yield_only_bo.py --dry-run
```

Optional safe BO-MCP validation of the intake only:

```bash
uv run python recreate_robochemflex_yield_only_bo.py --dry-run --validate-intake
```

The default source export is:

```text
artifacts/recreated_robochemflex_yield_bo_20260725/failed_measurement_retry_continuation_20260726T184638Z/bo_campaign_export.csv
```

## 2. Create and seed the new yield-only BO-MCP campaign (requires user confirmation)

This creates a new BO-MCP campaign and imports the 20 valid historical results with only `yield_percent` as an objective. It does **not** contact RoboFlex hardware.

```bash
uv run python recreate_robochemflex_yield_only_bo.py \
  --execute-create-seed \
  --confirm-create-seed \
  --validate-intake
```

After it succeeds, inspect the artifact directory for:

- `bo_campaign_id.txt` — new yield-only BO campaign id
- `yield_only_intake.json`
- `yield_only_seed_results.json`
- `seed_audit.jsonl`
- `bo_campaign_export.csv`

## 3. Continuation preflight (safe after campaign id exists)

Replace `<NEW_YIELD_ONLY_CAMPAIGN_ID>` with the id from `bo_campaign_id.txt`. This checks the new BO campaign, the source mixed-objective campaign, and the active RoboFlex campaign read-only.

```bash
uv run python continue_robochemflex_yield_only_bo.py \
  --campaign-id <NEW_YIELD_ONLY_CAMPAIGN_ID> \
  --dry-run \
  --live-read-checks
```

## 4. Later hardware start (requires explicit user confirmation)

Only after the user confirms, run one autonomous yield-only continuation measurement. The script will generate/reuse one BO suggestion, verify RoboFlex request equivalence, submit to the same active RoboFlex campaign, poll the run, and submit a yield-only BO result only if the analysis reports `pass=true`.

```bash
uv run python continue_robochemflex_yield_only_bo.py \
  --campaign-id <NEW_YIELD_ONLY_CAMPAIGN_ID> \
  --execute \
  --confirm-autonomous-hardware \
  --max-new-measurements 1
```


## Measurement #22 safe retry continuation (prepared 2026-07-27)

This wrapper is pinned to yield-only BO campaign `1970655b-a702-4963-874b-6973489cc89d`, required pending suggestion `31d5114e-3796-4b21-9d5f-d7e9a31378b0`, and original failed sample `bo_31d5114e-3` / run `R0068`. It treats RoboFlex error `zero-size array to reduction operation minimum which has no identity` as a retryable stochastic NMR/analysis null-result failure only if RoboFlex is still `mode=hardware`, `phase=running`, `progress.state=awaiting_run`, and has no queued/running/active runs.

Safe read-only preflight:

```bash
uv run python continue_robochemflex_yield_only_bo_retry22.py --dry-run --live-read-checks
```

Hardware execution, only after explicit operator/user confirmation:

```bash
uv run python continue_robochemflex_yield_only_bo_retry22.py \
  --execute \
  --confirm-autonomous-hardware
```

The first retry sample is `bo_31d5114e-3_r2`, followed by `_r3` and `_r4` if needed. The script submits a BO result only when a retry returns `pass=true` with finite yield. If all retry attempts fail, it pauses/stops without BO submission. After #22 succeeds, it continues one-at-a-time until the invocation budget reaches 7 new valid results from now or the campaign has 28 valid BO results total.

## Retry policy implemented for continuation

For each BO suggestion, the script performs the initial RoboFlex run plus up to `--max-nmr-retries 3` retry submissions when all of the following are true:

1. the run reached analysis rather than a platform/device failure;
2. the analysis/QC did not pass; and
3. finite yield/peak-like evidence is present in the RoboFlex result payload.

It stops without submitting a BO objective result on true device/platform failures, no-peak/no-evidence failures, systemic failures, multiple pending BO suggestions, failed request-equivalence checks, duplicate visible sample names, or exhausted retry budget.

## What still requires confirmation

- Creating/seeding the yield-only BO-MCP campaign.
- Starting any hardware continuation run on RoboFlex.
- Any decision to stop the active RoboFlex campaign or request a new RoboFlex setup; these scripts do not do that.
