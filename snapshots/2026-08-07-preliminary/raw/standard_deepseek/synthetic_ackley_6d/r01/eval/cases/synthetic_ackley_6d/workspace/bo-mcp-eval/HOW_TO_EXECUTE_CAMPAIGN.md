# HOW TO EXECUTE: Ackley-6D BayBE Benchmark Campaign

## Overview

Synthetic benchmark: Bayesian optimisation of the **Ackley function** in 6
normalised dimensions using the **BayBE** backend via BO-MCP.

- **Search space**: 6 continuous parameters `x_1` … `x_6` ∈ [0, 1].
- **Objective**: `surface_response` (maximise, unit `normalized_unitless`).
- **Evaluator**: deterministic Python function — no chemistry, no PySCF.
- **Budget**: 60 attempted evaluations (CLI-controlled, not baked into intake).
- **Campaign marker** (in name): `akg-eval-b42cee6306f44fd696958bf6e0ead612`

## Environment Requirements

| Variable            | Required | Description                          |
|---------------------|----------|--------------------------------------|
| `BO_MCP_API_URL`    | **yes**  | BO-MCP REST API base URL             |
| `BO_MCP_API_KEY`    | **yes**  | API key for BO-MCP                   |

The script runs inside the repo's `uv` environment:

```bash
uv run python run_ackley_benchmark.py [OPTIONS]
```

## Exact Execution Command

### Fresh campaign (first run)

```bash
uv run python run_ackley_benchmark.py \
  --max-evals 60 \
  --poll-s 180 \
  --heartbeat-s 1800 \
  --stop-file STOP \
  --artifact-dir artifacts \
  --random-seed 42 \
  --initial-design-size 12
```

### Resume a paused/completed campaign

```bash
uv run python run_ackley_benchmark.py \
  --campaign-id <CAMPAIGN_ID> \
  --max-evals 60 \
  --poll-s 180 \
  --heartbeat-s 1800 \
  --stop-file STOP \
  --artifact-dir artifacts
```

## CLI Arguments

| Flag                    | Default      | Description                                      |
|-------------------------|--------------|--------------------------------------------------|
| `--campaign-id`         | `None`       | Resume existing campaign; omit to create new one |
| `--max-evals`           | `60`         | Max attempted evaluations this invocation        |
| `--poll-s`              | `180`        | Seconds between loop iterations                  |
| `--heartbeat-s`         | `1800`       | Seconds between heartbeat log lines              |
| `--stop-file`           | `STOP`       | Path checked each iteration; deleted on trigger  |
| `--artifact-dir`        | `artifacts`  | Output directory for results/diagnostics/summary |
| `--random-seed`         | `42`         | Campaign RNG seed                                |
| `--initial-design-size` | `12`         | Sobol warm-up points (2×d)                       |

## Stop / Resume Behaviour

- **Stop**: create a file named `STOP` (or whatever `--stop-file` points at)
  in the working directory.  The script checks for it at the top of each
  iteration, deletes it, prints `[EVENT]`, and exits through the normal
  shutdown path (diagnostics → pause → summary).
- **Resume**: re-run the same command with `--campaign-id <ID>`.  The script
  detects the campaign status and resumes/reopens automatically.
- **Pause on exit**: the script pauses the campaign at shutdown so it can
  always be resumed.  It never terminates the campaign.

## Monitor-Friendly Tagged Output

The script prints unbuffered tagged lines to stdout:

| Tag           | Meaning                                          |
|---------------|--------------------------------------------------|
| `[EVENT]`     | State changes, lifecycle transitions             |
| `[ALERT]`     | Failures, stop conditions, warnings              |
| `[RESULT]`    | Per-evaluation analysis (params + objective)     |
| `[HEARTBEAT]` | Periodic liveness ping                           |

Everything else goes to the result log on disk.

## Output Artifacts

All artifacts land in `--artifact-dir` (default `artifacts/`):

| File               | Format   | Description                                      |
|--------------------|----------|--------------------------------------------------|
| `results.jsonl`    | JSONL    | One row per evaluated candidate (see schema below)|
| `diagnostics.json` | JSON     | End-of-invocation campaign diagnostics           |
| `summary.json`     | JSON     | Final summary: best values, counts, campaign_id  |

### `results.jsonl` row schema

```json
{
  "evaluation_index": 1,
  "parameter_values": {"x_1": 0.5, "x_2": 0.5, "x_3": 0.5, "x_4": 0.5, "x_5": 0.5, "x_6": 0.5},
  "objective_values": {"surface_response": 1.0},
  "status": "success",
  "raw_response": 0.0
}
```

- `status` is one of `success`, `failed`, or `submit_rejected`.
- `failure_reason` is present only for non-success rows.
- `raw_response` is the un-normalised Ackley value (optional but always present for successes).

## Duplicate Detection

The script tracks all previously evaluated parameter sets (loaded from BO-MCP on
resume).  Before evaluating a suggestion it checks for duplicates (12 decimal
places of precision).  Duplicates are rejected via `update_suggestion_status`
and a new suggestion is requested — without consuming the evaluation budget.
After 10 consecutive duplicates the script stops to avoid an infinite loop
(typically indicates the BO model has converged on a local optimum).
- `failure_reason` is present only for non-success rows.
- `raw_response` is the un-normalised Ackley value (optional but always present for successes).

## Extracting the Campaign ID

The final line of stdout is always:

```
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

Parse this line to obtain the campaign ID for resumption or reporting.

## Ackley Evaluator Definition

For reference, the evaluator implements:

```
z_i    = -40 + 80 × x_i          (i = 1…6)
d      = 6
classic = -20·exp(-0.2·√(Σz_i²/d)) - exp(Σcos(2π·z_i)/d) + 20 + e
raw_response = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
```

No noise is added.  The global optimum is at `x_i = 0.5` (all i), yielding
`surface_response = 1.0`.