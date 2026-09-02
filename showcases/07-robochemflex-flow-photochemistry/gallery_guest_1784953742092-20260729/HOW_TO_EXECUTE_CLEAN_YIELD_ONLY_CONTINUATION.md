# Clean yield-only BO continuation after discarding R0068+

This path recreates the yield-only BO-MCP campaign from clean data only:

- original 20 valid historical seed rows;
- retained measurement #21: RoboFlex `R0067`, sample `bo_cc26e7f1-b`, yield `58.811245%`;
- explicitly excludes `R0068` and every later RoboFlex run/result.

It does **not** mutate RoboFlex during recreation. Hardware is contacted only by the final continuation command, and only with `--execute --confirm-autonomous-hardware` plus the operator-provided `ROBRIDGE_POST_ADAPTER`.

## 1) Create and seed the clean 21-row yield-only BO-MCP campaign

Preflight only, including BO-MCP intake validation and an audit of observed excluded runs:

```bash
uv run python recreate_robochemflex_yield_only_clean21.py \
  --validate-intake \
  --artifact-dir artifacts/yield_only_clean21_preflight_$(date -u +%Y%m%dT%H%M%SZ)
```

Create/seed BO-MCP (no RoboFlex/hardware calls):

```bash
CLEAN_ARTIFACT_DIR="artifacts/yield_only_clean21_recreation_$(date -u +%Y%m%dT%H%M%SZ)"
uv run python recreate_robochemflex_yield_only_clean21.py \
  --execute-create-seed \
  --confirm-create-seed \
  --validate-intake \
  --artifact-dir "$CLEAN_ARTIFACT_DIR"
export CLEAN_YIELD_ONLY_CAMPAIGN_ID="$(cat "$CLEAN_ARTIFACT_DIR/bo_campaign_id.txt")"
echo "$CLEAN_YIELD_ONLY_CAMPAIGN_ID"
```

Before continuing, inspect:

```bash
cat "$CLEAN_ARTIFACT_DIR/preflight_summary.json"
cat "$CLEAN_ARTIFACT_DIR/discard_audit.json"
cat "$CLEAN_ARTIFACT_DIR/recreation_summary.json"
```

Expected: `final_result_count` is `21`; retained run ids contain only `R0067`; excluded observed run ids include any `R0068+` artifacts found; `contacted_roboflex` is `false`.

## 2) Preflight the clean continuation

This is read-only against BO-MCP/RoboFlex and submits no runs:

```bash
uv run python continue_robochemflex_yield_only_clean21.py \
  --campaign-id "$CLEAN_YIELD_ONLY_CAMPAIGN_ID" \
  --live-read-checks
```

Expected: BO result count is `21`, target total is `28`, remaining valid results is `7`, and RoboFlex reports the expected active campaign in hardware mode and ready/running/awaiting-run state.

## 3) Continue for the remaining overnight target

The clean campaign starts from 21 valid results, so target 28 requires 7 new valid measurements.

```bash
uv run python continue_robochemflex_yield_only_clean21.py \
  --campaign-id "$CLEAN_YIELD_ONLY_CAMPAIGN_ID" \
  --execute \
  --confirm-autonomous-hardware \
  --max-new-measurements 7 \
  --target-total-results 28 \
  --max-nmr-retries 3
```

The retry policy submits a BO result only when RoboFlex result `pass=true` with finite yield. Stochastic NMR/analysis failures are retried up to 3 times when the platform is healthy/idle; unsafe failures stop without submitting a BO result.
