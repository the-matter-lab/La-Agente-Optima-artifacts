# Ackley 6D BO-MCP benchmark: how to execute

Ownership marker: `akg-eval-6e5b5396372b4b4ca56533a3787738d2`  
Cache-buster nonce: `7b86fd35-b943-4816-b7ba-82e865684bf2`

This package implements the requested BO-MCP-owned synthetic benchmark:
- objective: `surface_response`
- direction: `maximize`
- unit: `normalized_unitless / normalized unitless response`
- search space: `x_1..x_6`, each continuous on `[0.0, 1.0]`
- evaluation budget: at most **60 attempted** objective evaluations total
- duplicate normalized coordinates are rejected without evaluation and do **not** count toward the 60-attempt budget
- successful evaluations are submitted to BO-MCP; failed attempted evaluations are recorded locally and marked `expired` in BO-MCP so the same 60-attempt cap is preserved across resumes

## Smoke test status

A bounded smoke test was run in this container on **July 30, 2026**.
It created and paused this owned campaign after exactly **1** successful BO iteration:

- campaign id: `2238ed7e-eae4-4909-83d2-03a8e330a602`
- campaign id file: `artifacts/ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/2238ed7e-eae4-4909-83d2-03a8e330a602/campaign_id.txt`
- latest artifact dir: `artifacts/ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/2238ed7e-eae4-4909-83d2-03a8e330a602`

Because the smoke test already consumed 1 attempted evaluation, the most direct way to finish the benchmark from that campaign is to resume it for up to **59** additional attempts.

## Required environment

The script expects these environment variables:
- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

They were already present during smoke testing in this container.

## Recommended command to continue the smoke-tested campaign

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.py \
  --campaign-id 2238ed7e-eae4-4909-83d2-03a8e330a602 \
  --invocation-attempt-budget 59
```

The script will still stop automatically at the global 60-attempt cap even if you pass a larger invocation budget.

## Command to create a fresh owned campaign instead

If you intentionally want a new campaign for this same invocation marker, omit `--campaign-id`:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.py
```

Every new campaign created by this script includes the exact ownership marker `akg-eval-6e5b5396372b4b4ca56533a3787738d2` in its campaign name.
Do **not** resume or report a campaign that lacks that marker.

## Runtime behavior

- The script uses `BoMcpClient.from_env()` and keeps BO lifecycle ownership in BO-MCP.
- It validates intake before creating a campaign.
- It resumes paused campaigns and reopens completed campaigns automatically.
- It checks for a stop file before each suggestion request.
- At the end of each invocation it pauses the campaign instead of terminating it.
- It never evaluates the same normalized point twice.
- It writes one artifact row per evaluated candidate.

## Monitor-friendly stdout tags

The entrypoint emits only these user-facing stdout tags plus the single campaign-id line:
- `[EVENT]` state transitions, artifact updates, stop conditions
- `[RESULT]` one line per attempted objective evaluation
- `[HEARTBEAT]` liveness updates during long runs
- `BO_MCP_CAMPAIGN_ID=<campaign_id>` once per invocation

## Stop file

Default stop file path:

```text
STOP
```

To request a clean stop before the next suggestion is generated:

```bash
touch STOP
```

The script deletes the file after noticing it so a later resume is not blocked by a stale marker.

## Output artifacts

Per-campaign artifacts are written under:

```text
artifacts/ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/<campaign_id>/
```

Important files:
- `evaluations.jsonl` — one JSON row per evaluated candidate, including:
  - `evaluation_index`
  - `parameter_values`
  - `objective_values`
  - `status`
  - `failure_reason`
  - `raw_response`
- `evaluated_candidates.csv` — flat table of all evaluated candidates and statuses
- `summary.json` — current best point and aggregate counts
- `report.md` — human-readable report including the required evaluated-candidate table
- `run.log` — detailed run log
- `campaign_id.txt` — contains the exact line `BO_MCP_CAMPAIGN_ID=<campaign_id>`

The workspace root also contains:
- `campaign_manifest.json` — package module paths, runner path, latest artifact dir, latest campaign id

## Validation checklist after a run

1. Confirm stdout includes a line of the form `BO_MCP_CAMPAIGN_ID=<campaign_id>`.
2. Open `summary.json` and verify:
   - `attempted_evaluations <= 60`
   - `successful_evaluations <= attempted_evaluations`
3. Open `report.md` or `evaluated_candidates.csv` to review:
   - best normalized coordinates
   - best `raw_response`
   - best `surface_response`
   - counts of successful and attempted evaluations
   - the full evaluated-candidate table with statuses
4. If you resumed the smoke-tested campaign, expect the final campaign total to stop at 60 attempted evaluations.

## Main files

- runner: `run_ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2.py`
- package directory: `ackley6d_akg_eval_6e5b5396372b4b4ca56533a3787738d2/`
- manifest: `campaign_manifest.json`
