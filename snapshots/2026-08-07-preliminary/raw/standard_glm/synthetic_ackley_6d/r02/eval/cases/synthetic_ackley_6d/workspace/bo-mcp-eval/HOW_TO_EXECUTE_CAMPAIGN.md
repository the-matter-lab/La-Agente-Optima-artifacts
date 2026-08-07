# HOW TO EXECUTE CAMPAIGN — Ackley 6-D Synthetic Benchmark

**Cache-buster nonce**: `221d8dd7-74d6-4aa1-91de-bc9e69d726c3`
**Campaign ownership marker**: `akg-eval-1115ffcb87fa4a6dbb0454263fb25553`

---

## Overview

This campaign optimizes the negated-and-rescaled Ackley function over 6
continuous normalized dimensions via the BO-MCP server.  The evaluator is
deterministic and purely synthetic — no PySCF, CREST, MOF, or chemistry
tools are invoked.

| Item | Value |
|------|-------|
| Search space | x_1..x_6 ∈ [0.0, 1.0] continuous |
| Objective | `surface_response` (maximize, normalized_unitless) |
| Budget | 60 attempted evaluations |
| Backend | botorch |
| Acquisition | expected_improvement |
| Initial design | 10 Sobol points |
| Batch size | 1 (sequential) |
| Random seed | 2024 |

---

## Environment Requirements

| Variable | Required | Description |
|----------|----------|-------------|
| `BO_MCP_API_URL` | **yes** | BO-MCP REST API base URL |
| `BO_MCP_API_KEY` | **yes** | BO-MCP API key |
| `ARTIFACT_DIR` | no | Default artifact output directory (default: cwd) |
| `STOP_FILE` | no | Default stop-file path (default: `STOP`) |

---

## Execution Command

```bash
cd <workspace>/bo-mcp-eval

# Full run (creates campaign, runs 60 evaluations):
python3 run_ackley_bo.py --artifact-dir ./artifacts

# Resume a paused/killed run:
python3 run_ackley_bo.py \
    --campaign-id <CAMPAIGN_ID> \
    --artifact-dir ./artifacts
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--campaign-id` | *(none)* | Existing campaign ID to resume |
| `--artifact-dir` | `$ARTIFACT_DIR` or `.` | Where result artifacts are written |
| `--stop-file` | `$STOP_FILE` or `STOP` | File whose existence triggers graceful pause |
| `--poll-s` | 180 | Retry delay on transient failures (seconds) |
| `--heartbeat-s` | 1800 | Interval between `[HEARTBEAT]` lines |

---

## Stop / Resume Behavior

### Stopping

Create the stop file to request a graceful pause:

```bash
touch STOP   # (or the path passed via --stop-file)
```

The script checks for the stop file at the **top of each loop iteration**
(before generating a new suggestion).  When detected it:

1. Prints `[EVENT] Stop file detected — pausing campaign`
2. Deletes the stop file (so a resume command is not blocked by a stale marker)
3. Pauses the campaign via the BO-MCP lifecycle API
4. Exits cleanly

**Important**: the stop file is **not** checked between evaluation and
result submission — the script always submits a completed evaluation
before honouring the stop request.

### Resuming

Re-run the same command with `--campaign-id`:

```bash
uv run python run_ackley_bo.py \
    --campaign-id <CAMPAIGN_ID> \
    --artifact-dir ./artifacts
```

The script will:
- Resume a paused campaign, or reopen a completed one
- Reload prior artifact rows from the JSONL file
- Continue the BO loop from where it left off

---

## Tagged Output Lines

The script prints unbuffered tagged lines for monitor integration:

| Tag | Meaning |
|-----|---------|
| `[EVENT]` | State changes (campaign created, resumed, paused, loop finished) |
| `[ALERT]` | Failures, rejected suggestions, transient errors |
| `[RESULT]` | Per-evaluation analysis (eval index, surface_response, raw_response, best so far) |
| `[HEARTBEAT]` | Liveness check (campaign ID, counts, best surface_response) |

All other output goes to the run log on disk.

---

## Result Artifacts

All artifacts are written to `--artifact-dir` (default: current directory).

| File | Format | Description |
|------|--------|-------------|
| `ackley_results.jsonl` | JSON Lines | One row per attempted evaluation (append-only) |
| `ackley_summary.json` | JSON | Final summary with best point, counts, and full table |
| `ackley_table.txt` | Text | Human-readable table of all evaluations |

### JSONL Row Schema

Each line in `ackley_results.jsonl`:

```json
{
  "evaluation_index": 1,
  "parameter_values": {"x_1": 0.5, "x_2": 0.5, "x_3": 0.5, "x_4": 0.5, "x_5": 0.5, "x_6": 0.5},
  "objective_values": {"surface_response": 0.123456},
  "status": "success",
  "raw_response": -12.345678
}
```

Failed evaluations include `"failure_reason"` and omit `raw_response`.

### Summary JSON Schema

```json
{
  "best_normalized_coordinates": {"x_1": ..., "x_2": ..., "x_3": ..., "x_4": ..., "x_5": ..., "x_6": ...},
  "best_raw_response": -0.001234,
  "best_surface_response": 0.999945,
  "attempted_evaluations": 60,
  "successful_evaluations": 60,
  "all_evaluations": [ ... ]
}
```

---

## Expected Runtime / Behavior

- **Per evaluation**: ~1–5 seconds (BO-MCP suggestion generation dominates;
  the Ackley evaluator itself is sub-millisecond).
- **Full 60-evaluation run**: ~5–15 minutes depending on BO-MCP server load
  and GP model fitting time.
- The campaign is **paused** (not terminated) at the end of each invocation,
  so it can be resumed or reopened for continuation.
- The script never sets `max_iterations` in the campaign intake — the 60-eval
  budget is enforced client-side only.

---

## Campaign Ownership

Every campaign created by this script includes the marker
`akg-eval-1115ffcb87fa4a6dbb0454263fb25553` in its name.  The script
refuses to adopt a campaign that lacks this marker.
