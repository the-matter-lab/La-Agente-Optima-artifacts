# How to Execute the 6D Ackley BO-MCP Benchmark Campaign

## Prerequisites

- Docker container with the BO-MCP API running at `$BO_MCP_API_URL`
- `BO_MCP_API_URL` and `BO_MCP_API_KEY` environment variables set
- Python environment with `uv` (the repo root is `/app`)

## Command

```bash
cd <workspace>   # the directory containing run_ackley_benchmark.py

uv run python run_ackley_benchmark.py \
    --max-evals 60 \
    --artifact-dir ackley_artifacts \
    --poll-s 180 \
    --heartbeat-s 1800 \
    --stop-file STOP \
    --log-path ackley_run.log
```

To resume a paused/completed campaign:

```bash
uv run python run_ackley_benchmark.py \
    --campaign-id <CAMPAIGN_ID> \
    --max-evals 60 \
    --artifact-dir ackley_artifacts
```

## Tagged stdout lines

The script emits unbuffered tagged lines the monitor can match:

| Tag          | Meaning                                              |
|-------------|------------------------------------------------------|
| `[EVENT]`   | State changes (create, resume, pause, loop decision) |
| `[ALERT]`   | Failures, stop-file detection, submission errors     |
| `[RESULT]`  | Per-evaluation summary (index, surface_response, params) |
| `[HEARTBEAT]` | Liveness ping every `--heartbeat-s` seconds        |

## Stop file

Create a file named `STOP` (or whatever `--stop-file` points at) in the
working directory to request a graceful shutdown at the next iteration
boundary.  The script deletes the file on detection so a subsequent
`--campaign-id` resume is not stopped by a stale marker.

## Output artifacts

- **`ackley_artifacts/evaluations.jsonl`** — one JSON object per evaluated
  candidate with fields: `evaluation_index`, `timestamp_utc`,
  `parameter_values` (`x_1`…`x_6`), `objective_values` (`surface_response`),
  `raw_response`, `status`, `failure_reason`.
- **`ackley_run.log`** — copy of all tagged stdout lines (if `--log-path`
  is set).
- **`BO_MCP_CAMPAIGN_ID=<id>`** — printed on the last line of stdout.

## Campaign ID

The campaign ID is printed as the last line of stdout:

```
BO_MCP_CAMPAIGN_ID=<uuid>
```

The main agent should capture this for reporting.  The campaign name
always includes the marker `akg-eval-154cf4595f874983bf81ab79c7d27e0a`.

## Validation

After execution, verify:

1. `ackley_artifacts/evaluations.jsonl` has exactly 60 rows — the benchmark
   contract requires exactly 60 attempted evaluations.  The script enforces
   this budget; the only legitimate shortfall is a stop-file interrupt or
a catastrophic generation failure after 10 consecutive retries.
2. The best `surface_response` approaches 1.0 (global optimum at
   x_i = 0.5 for all i).
3. No duplicate parameter vectors appear in the artifact.