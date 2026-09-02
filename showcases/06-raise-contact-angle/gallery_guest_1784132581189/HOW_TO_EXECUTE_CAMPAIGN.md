# How to Execute the Clean Seeded Ethanol + SDS BO/RAISE Campaign

## Files
- Entry point: `continue_ethanol_sds_contact_angle_65.py`
- Alternate entry point: `run_ethanol_sds_contact_angle_65.py`
- Package: `ethanol_sds_contact_angle_65/`
- Manifest: `campaign_manifest.json`
- Historical exports used for clean seeding:
  - `artifacts/ethanol_sds_contact_angle_65/20260715T170509Z__5be855ea/campaign_export.csv`
  - `artifacts/ethanol_sds_contact_angle_65/20260715T180237Z__e799b16b/campaign_export.csv`

## What changed
This workflow now creates a **new clean BO-MCP campaign** in the corrected feasible search space:
- `Ethanol` in `0-50` v/v%
- `SDS` in `0-1` w/v%

It seeds that fresh campaign from both prior campaigns, but only with rows that are:
- finite,
- inside the corrected search space, and
- **not** fallback / penalty rows (`static_contact_angle != 180.0`).

If the same parameter pair appears in both exports, the script deduplicates by the rounded 6-decimal `(Ethanol, SDS)` pair and keeps the first copy encountered. The default source order is:
1. original campaign `5be855ea-96e2-4a4b-b564-d06bf18de9a5`
2. corrected campaign `e799b16b-d208-4d60-a115-72a67cac3130`

That means the original campaign copy is kept for rows that were later re-seeded into the corrected campaign.

## Historical rows included / excluded by source
### Original campaign `5be855ea-96e2-4a4b-b564-d06bf18de9a5`
From `artifacts/ethanol_sds_contact_angle_65/20260715T170509Z__5be855ea/campaign_export.csv`:
- total rows: `14`
- seeded rows kept: `13`
- excluded rows: `1`
- duplicate rows dropped: `0`

Excluded row:
- `Ethanol=60.0`, `SDS=1.0`, `static_contact_angle=180.0`
- excluded because it is both a fallback penalty row and outside the corrected `Ethanol <= 50` space

### Corrected campaign `e799b16b-d208-4d60-a115-72a67cac3130`
From `artifacts/ethanol_sds_contact_angle_65/20260715T180237Z__e799b16b/campaign_export.csv`:
- total rows: `20`
- valid non-penalty in-space rows before dedup: `18`
- seeded rows newly kept: `5`
- excluded rows: `2`
- duplicate rows dropped: `13`

Excluded fallback penalty rows:
- `Ethanol=35.616705`, `SDS=1.0`, `static_contact_angle=180.0`
- `Ethanol=30.473108`, `SDS=0.999931`, `static_contact_angle=180.0`

### Combined clean seed set
- combined valid non-penalty in-space rows before dedup: `31`
- combined duplicates dropped: `13`
- **unique seeded rows submitted to the new clean campaign: `18`**

The 5 unique rows contributed only by the corrected campaign are:
- `(20.828506, 1.0) -> 71.0`
- `(32.143061, 1.0) -> 68.61`
- `(29.85829, 1.0) -> 68.859`
- `(30.102219, 0.999948) -> 69.013`
- `(1.553901, 0.809939) -> 71.763`

## Objective and stopping rule
The BO objective remains a **match** objective targeting `65` degrees static contact angle.

The run stops early if any measured contact angle lands in:
- `64` to `66` degrees inclusive

## Failure handling change
Measurement failures are no longer submitted to BO as `180.0` penalty objectives.

New behavior for BO-suggested candidates:
1. run the candidate in RAISE,
2. if RAISE reports a measurement-failure / retry-type error, retry the **same candidate**,
3. default retries: `2` retries after the first failed attempt (`3` total attempts max),
4. if measurement still fails, record the failure in local artifacts and mark the BO suggestion as `expired`,
5. do **not** submit a fake measured objective for that failed measurement.

This keeps BO from learning that a measurement failure is a bad physical contact angle.

## Default continuation budget
Default per-invocation BO budget:
- `--bo-iteration-budget 5`

Why `5`?
- It is within the requested modest 4-6 range.
- It is large enough to make progress from the clean 18-point seed set.
- It is still small enough to keep each manual invocation bounded and resumable.

## Prerequisites
The script expects these environment variables to already be available:
- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

It runs through the repository `uv` environment and uses the repository BO-MCP client plus the RAISE evaluator.

## Exact command to create and run the new clean seeded campaign now
```bash
uv run python continue_ethanol_sds_contact_angle_65.py
```

That command will:
- create a fresh clean campaign,
- seed it with the 18 unique valid historical rows above,
- then attempt up to 5 new BO iterations for this invocation,
- retry measurement failures up to 2 times,
- and pause the campaign at the end unless it is terminated explicitly.

## Resume the same clean campaign later
```bash
uv run python continue_ethanol_sds_contact_angle_65.py --campaign-id <NEW_CLEAN_CAMPAIGN_ID>
```

## Useful options
Change the per-invocation BO budget:

```bash
uv run python continue_ethanol_sds_contact_angle_65.py --bo-iteration-budget 4
```

Change measurement retries:

```bash
uv run python continue_ethanol_sds_contact_angle_65.py --measurement-retries 1
```

Create and seed only, without attempting new BO suggestions in that invocation:

```bash
uv run python continue_ethanol_sds_contact_angle_65.py --bo-iteration-budget 0
```

Change the evaluator timeout:

```bash
uv run python continue_ethanol_sds_contact_angle_65.py --raise-timeout-s 700
```

Terminate instead of pause at the end:

```bash
uv run python continue_ethanol_sds_contact_angle_65.py --terminate-on-exit
```

## Artifacts to inspect after a run
Each invocation writes a new artifact directory under:

```text
artifacts/ethanol_sds_contact_angle_65/
```

Typical files include:
- `run_context.json`
- `seed_filter_summary.json`
- `seed_upload.json` (when a fresh campaign is seeded)
- `evaluations.jsonl`
- `diagnostics.json` (best effort)
- `campaign_export.csv` (best effort)
- `run_summary.json`

The latest artifact directory is also recorded in `campaign_manifest.json`.

## How to validate the outcome
1. Read stdout for the new campaign id, per-source seed counts, each submitted BO experiment, and the stop reason.
2. Check `seed_filter_summary.json` to confirm the clean 18-row seed set and the per-source exclusions / duplicates.
3. Check `seed_upload.json` to confirm BO-MCP accepted the seeded rows.
4. Check `evaluations.jsonl` for each new BO evaluation and any expired measurement-failure suggestions.
5. Check `run_summary.json` for the best observed angle and final campaign status.
6. Inspect `campaign_export.csv` for the BO-MCP campaign export.

