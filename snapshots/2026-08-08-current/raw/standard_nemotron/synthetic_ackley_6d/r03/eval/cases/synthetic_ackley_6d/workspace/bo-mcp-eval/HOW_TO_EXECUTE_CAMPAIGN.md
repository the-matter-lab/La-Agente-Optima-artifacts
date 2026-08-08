# How to Execute the 6D Ackley BO Campaign

## Campaign Overview
- **Campaign name pattern**: `ackley_6d_baybe_akg-eval-85fb74eb00b449cd9dc81b7e98d95efc`
- **Backend**: `baybe`
- **Objective**: Maximize `surface_response` (normalized 6D Ackley function)
- **Total evaluation budget**: 60 attempted evaluations (including any smoke testing)
- **Search space**: 6 continuous parameters `x_1` through `x_6` in `[0.0, 1.0]`

## Current State (After Repair)
- **1 evaluation already completed** and recorded in local artifact `ackley_6d_results/evaluations.jsonl`
- **59 evaluations remaining** in the hard budget of 60
- **Existing campaign ID**: `69f4de86-a618-4572-ae3f-445ef7bc116f` (marker preserved)

## Prerequisites
1. **BO-MCP server** running and accessible
2. **Environment variables** set:
   ```bash
   export BO_MCP_API_URL="http://api:8000"  # or your BO-MCP server URL
   export BO_MCP_API_KEY="[REDACTED]"      # API key for authentication
   ```

## Execution Commands

### Continue Existing Campaign (RECOMMENDED)
```bash
cd /app/outputs/cells/ackley_standard_nemotron_baybe_duplicate_fix_r03/eval/cases/synthetic_ackley_6d/workspace/bo-mcp-eval
uv run python run_ackley_6d.py --campaign-id 69f4de86-a618-4572-ae3f-445ef7bc116f --max-evaluations 59
```

### Start Fresh Campaign (Alternative)
If the existing campaign cannot be resumed reliably, create a new one. The local artifact will still preserve the 1 completed evaluation for final reporting, but BO-MCP will start a new campaign.
```bash
uv run python run_ackley_6d.py --max-evaluations 59 --results-dir ackley_6d_results
```
**Note**: The `--results-dir ackley_6d_results` preserves the existing local artifact. The new campaign will have a different ID but final reports merge local artifact data.

### With Custom Parameters
```bash
uv run python run_ackley_6d.py \
    --campaign-id 69f4de86-a618-4572-ae3f-445ef7bc116f \
    --max-evaluations 59 \
    --poll-s 180 \
    --heartbeat-s 1800 \
    --stop-file STOP \
    --results-dir ackley_6d_results \
    --random-seed 42 \
    --initial-design-size 10
```

## Key Files
- **Entry script**: `run_ackley_6d.py`
- **Campaign package**: `ackley_6d_bo/`
  - `search_space/__init__.py` - 6D Ackley function implementation
  - `intake/__init__.py` - Campaign intake construction
  - `evaluation/__init__.py` - Deterministic evaluator (loads existing artifact state)
  - `orchestration/__init__.py` - BO-MCP client orchestration (submits BO-MCP-compatible payloads)
- **Campaign manifest**: `campaign_manifest.json`

## Stop File Mechanism
- Create a file named `STOP` (or custom path via `--stop-file`) in the working directory to request graceful pause
- The script checks for this file at the top of each optimization loop iteration
- When detected, the script deletes the file, pauses the campaign via BO-MCP, and exits
- To resume, re-run the same command with `--campaign-id <CAMPAIGN_ID>`

## Tagged Output Lines
The script emits structured log lines for monitoring:
- `[EVENT]` - State changes (campaign created, pausing, etc.)
- `[ALERT]` - Failures and stop conditions
- `[RESULT]` - Full per-experiment analysis (evaluation index, surface_response, raw_response, parameters)
- `[HEARTBEAT]` - Liveness indicator (every 30 minutes by default)

## Output Artifacts
All artifacts written to `--results-dir` (default: `ackley_6d_results/`):
- `evaluations.jsonl` - One JSON line per evaluation (append-only provenance)
- `final_report.json` - Complete final report with best point and candidate table

## Final Report Contents
The final report includes:
- `campaign_id` - BO-MCP campaign ID
- `best_normalized_coordinates` - Dict of best `x_1`..`x_6` values
- `best_raw_response` - Best raw_response value (unscaled)
- `best_surface_response` - Best surface_response value (normalized [0,1])
- `successful_evaluations` - Count of successful evaluations
- `attempted_evaluations` - Total attempted (including failures)
- `failed_evaluations` - Count of failed evaluations
- `candidate_table` - Array of all evaluated candidates with full details

## Required Single-Line Output
The script prints exactly one line at the end for the main agent:
```
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

## Evaluation Budget Tracking
- **Hard limit**: 60 attempted evaluations total across all runs (creation + resumptions)
- **Already used**: 1 (recorded in local artifact)
- **Remaining**: 59
- The `--max-evaluations` parameter bounds a single invocation only
- Do NOT set `max_iterations` in campaign intake (immutable; would cap forever)
- Each evaluation submitted to BO-MCP or written to local artifact counts toward the 60

## Duplicate Prevention
- The evaluator tracks seen points (rounded to 12 decimal places)
- Duplicate suggestions are marked as `failed` with `failure_reason="Duplicate point - already evaluated"`
- Duplicates still count toward the 60-evaluation budget
- On resume, evaluator loads `seen_points` and `evaluation_count` from existing `evaluations.jsonl`

## Chat Trace ID
For repairs or continuation, reference this trace ID: `03384678-d7c1-4415-be00-348d16eb8779`

## Nonce
`03384678-d7c1-4415-be00-348d16eb8779`