# Autonomous continuation: recreated RoboChemFlex BO campaign

This script is prepared but has **not** been executed and has **not** submitted any hardware runs.

## What it will do

- BO-MCP campaign: `ccbfc92e-c646-4943-a44d-9277f2f2d8d4`.
- Starts with the reviewed measurement #10 preview artifacts in `artifacts/recreated_robochemflex_yield_bo_20260725/measurement10_preview/`.
- Uses the existing pending suggestion id `98f9b554-6ff2-4a08-8e32-2fdecd211e10` and the exact reviewed RoboFlex request JSON for sample `bo_98f9b554-6`.
- Submits #10 first, polls the RoboFlex run every 180 s by default, fetches results, computes `yield_percent` and `green_score`, prints a completed-experiment analysis, then submits the BO-MCP result with the matching suggestion id.
- After #10, continues one experiment at a time: reuse exactly one pending suggestion if present, otherwise ask BO-MCP for one new suggestion, construct/validate the RoboFlex request, submit, poll, fetch, compute, print analysis, and submit BO result.
- Stops when either 11 new experiments have been completed in this invocation, BO-MCP reaches 20 total results, or the zero-yield/no-peak alert streak reaches the configured limit (default 5).

## Safety gates

Before each hardware submission the script stops unless all checks pass:

1. RoboFlex is in `hardware` mode.
2. Active RoboFlex campaign id/name matches `robochemflex_yield_bo_fresh_20260724T155503Z-20260724-175502`.
3. Phase/progress is `running` / `awaiting_run`.
4. Queue depth, queued/running counts, and active run ids are all zero/empty.
5. The sample name is not already visible in RoboFlex run notes or run parameters.
6. Request fixed fields/schema match the historical `robridge_results.jsonl` reference.
7. BO-MCP result count and pending suggestion shape are as expected.

The script requires both `--execute` and `--confirm-autonomous-hardware` before it can submit hardware runs. In this environment, `ROBRIDGE_POST_ADAPTER` must also be set by the operator for RoboFlex POST calls. Production monitoring defaults are `--poll-s 180`, `--heartbeat-s 1800`, `--zero-no-peak-streak-limit 5`, and quiet stdout enabled; stdout is intended for `start_monitor` and only reports state changes, alerts, heartbeats, and completed-experiment analyses.

## Dry-run / preflight

Static dry-run, no live BO/RoboFlex contact and no hardware writes:

```bash
uv run python continue_robochemflex_yield_bo_autonomous.py
```

Optional live read-only checks (no submissions, but contacts BO-MCP and RoboFlex GET endpoints):

```bash
uv run python continue_robochemflex_yield_bo_autonomous.py --live-read-checks
```

## Actual autonomous continuation command

Run only after operator review and after setting the approved RoboFlex POST adapter:

```bash
ROBRIDGE_POST_ADAPTER="$PWD/scripts/robridge_post_adapter.py" \
uv run python continue_robochemflex_yield_bo_autonomous.py \
  --execute \
  --confirm-autonomous-hardware \
  --poll-s 180 \
  --heartbeat-s 1800 \
  --zero-no-peak-streak-limit 5
```

## Artifacts

Actual execution creates a timestamped directory under:

`artifacts/recreated_robochemflex_yield_bo_20260725/autonomous_continuation_<UTCSTAMP>/`

Each measurement subdirectory contains:

- `suggestion.json`
- `candidate.json`
- `roboflex_request.json`
- `equivalence_report.json`
- `roboflex_status_before_submit.json`
- `roboflex_submission_response.json`
- `run_poll_trail.jsonl`
- `roboflex_final_run_record.json`
- `roboflex_result.json`
- `analysis.json`
- `bo_result_payload.json`
- `bo_result_response.json`

The run directory also contains `plan.json`, `COMMAND_NOTES.txt`, `summary.jsonl`, `summary.json`, and a best-effort BO campaign export.

## From-current resume after failed17 retry timeout (18 → 20)

Use this only for the current post-timeout state: BO campaign `ccbfc92e-c646-4943-a44d-9277f2f2d8d4` has exactly 18 BO results, no pending suggestions, RoboFlex is idle/awaiting_run in campaign `robochemflex_yield_bo_fresh_20260724T155503Z-20260724-175502`, and the old failed17 suggestion `a9f8598d-edd7-48fa-bbf6-b94ca3618912` must not be retried.

Dry-run only:

```bash
uv run python continue_robochemflex_yield_bo_from18.py
```

Optional live read-only preflight:

```bash
uv run python continue_robochemflex_yield_bo_from18.py --live-read-checks
```

Production command:

```bash
ROBRIDGE_POST_ADAPTER="$PWD/scripts/robridge_post_adapter.py" \
uv run python continue_robochemflex_yield_bo_from18.py \
  --execute \
  --confirm-autonomous-hardware \
  --expected-current-results 18 \
  --target-total-results 20 \
  --max-new-measurements 2 \
  --poll-s 180 \
  --heartbeat-s 1800 \
  --zero-no-peak-streak-limit 5 \
  --quiet-stdout
```

The from-current script resumes BO if paused, requires zero pending suggestions at start, generates one suggestion at a time, and if `generate_suggestions` times out it writes a recovery artifact, queries BO results and pending suggestions, and proceeds only when exactly one pending suggestion can be safely reused. Otherwise it pauses/exports BO and stops without any RoboFlex submission for that ambiguous state. Actual execution creates `artifacts/recreated_robochemflex_yield_bo_20260725/resume_from18_to20_<UTCSTAMP>/`.

