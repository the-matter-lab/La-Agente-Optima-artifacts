# Recreate BO-MCP campaign from completed RoboFlex history

This note is only for recreating the BO-MCP campaign after the BO-MCP stack reset. It does **not** contact RoboFlex and does **not** request/generate the next BO suggestion.

## Scope and safeguards

- Creates a fresh BO-MCP campaign with the existing `robochemflex_yield_bo` intake/search-space settings.
- Imports exactly these completed historical RoboFlex runs: `R0044, R0045, R0046, R0047, R0048, R0049, R0050, R0051, R0052`.
- Excludes invalid older runs `R0042` and `R0043` even if they are present in copied logs.
- Reads local history from `campaign_logs/roboflex_experiment_log_latest.csv`.
- Computes BO coordinates from the logged executed conditions and computes `green_score` with the existing package objective function.
- Submits historical rows without old `suggestion_id` values, because old BO-MCP campaign/suggestion ids are invalid after reset.
- Performs no `next_action` or `generate_suggestions` call.
- Imports with one idempotency key per run id and skips existing matching coordinates if rerun against an already-created campaign.
- Writes audit artifacts including the new `campaign_id`, preflight summary, exact result payloads, import audit, final BO-MCP result list, and CSV export.

## Non-mutating preflight

Run this first if you want to confirm local parsing before any BO-MCP mutation:

```bash
uv run python recreate_robochemflex_yield_bo_from_history.py --dry-run
```

Expected preflight output includes:

- `Prepared 9 historical result(s): R0044, ..., R0052`
- `RoboFlex/hardware calls: disabled by design`
- `BO suggestion generation: disabled by design`

## Actual recreation command

Run from the workspace root:

```bash
uv run python recreate_robochemflex_yield_bo_from_history.py \
  --campaign-name robochemflex_yield_baybe_recreated_20260725 \
  --run-nonce recreated-20260725-r0044-r0052 \
  --artifact-dir artifacts/recreated_robochemflex_yield_bo_20260725
```

The script requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` in the environment, via `BoMcpClient.from_env()`.

## If interrupted after campaign creation

If the script prints a new campaign id but exits before all imports finish, rerun against that same new campaign id:

```bash
uv run python recreate_robochemflex_yield_bo_from_history.py \
  --campaign-id <NEW_CAMPAIGN_ID> \
  --artifact-dir artifacts/recreated_robochemflex_yield_bo_20260725_resume
```

The rerun will skip any already-present matching coordinates and continue importing missing historical rows. It still will not call RoboFlex or generate BO suggestions.

## Artifacts to review after execution

In the artifact directory, review:

- `bo_campaign_id.txt` — the recreated BO-MCP campaign id.
- `historical_results_to_import.json` — exact BO result payloads for `R0044-R0052`.
- `import_audit.jsonl` — per-run submit/skip audit.
- `recreation_summary.json` — final counts and safeguards.
- `final_bomcp_results.json` — BO-MCP result rows after import.
- `bo_campaign_export.csv` — server export of the recreated campaign.

Success criteria: `recreation_summary.json` should show `expected_run_ids` as `R0044-R0052`, `generated_suggestions: false`, `contacted_roboflex: false`, and `final_result_count` at least 9 for a fresh campaign.
