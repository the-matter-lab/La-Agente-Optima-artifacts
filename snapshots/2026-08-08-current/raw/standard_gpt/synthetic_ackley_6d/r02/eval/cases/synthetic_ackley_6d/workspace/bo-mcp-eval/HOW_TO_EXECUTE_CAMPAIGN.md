# Ackley 6D BO-MCP Campaign

This campaign optimizes the deterministic synthetic Ackley 6D surface through BO-MCP only.

- Required ownership marker in campaign name: `akg-eval-88fef1120e594d599505287c7dd8ba7f`
- User nonce: `955b0c73-e93c-475f-b0fc-19ad0dfdc1ea`
- Search space: continuous `x_1..x_6` in `[0.0, 1.0]`
- Objective: `surface_response` (`maximize`, `normalized_unitless`)
- Global campaign cap: 60 submitted observations (`max_observations=60`)

## Required environment variables

- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

## Exact execution command

Run a fresh campaign:

```bash
PYTHONUNBUFFERED=1 python run_ackley_bomcp_benchmark.py --poll-s 180 --heartbeat-s 1800 --stop-file STOP
```

Resume an owned paused campaign:

```bash
PYTHONUNBUFFERED=1 python run_ackley_bomcp_benchmark.py --campaign-id <campaign_id> --poll-s 180 --heartbeat-s 1800 --stop-file STOP
```

For a bounded invocation, for example 5 more local evaluations this run:

```bash
PYTHONUNBUFFERED=1 python run_ackley_bomcp_benchmark.py --campaign-id <campaign_id> --invocation-attempt-budget 5 --poll-s 180 --heartbeat-s 1800 --stop-file STOP
```

## What the script does

- Creates a BO-MCP campaign when `--campaign-id` is omitted.
- Refuses to operate on campaigns whose name does **not** contain `akg-eval-88fef1120e594d599505287c7dd8ba7f`.
- Resumes paused campaigns automatically.
- Reopens completed campaigns only if they are still below the 60-observation cap.
- If a resumed campaign is already at the 60-attempt/60-observation cap, it emits a clean budget-exhausted summary and exits without requesting another suggestion.
- Rejects duplicate suggested points instead of evaluating them.
- Evaluates unique candidates locally with the deterministic Ackley 6D function and submits results back to BO-MCP.
- Pauses the campaign at the end of each invocation.

## Structured stdout tags

The script prints machine-friendly tagged lines:

- `[EVENT]` campaign lifecycle and run state changes
- `[ALERT]` duplicate suggestions, failures, or unexpected empty generations
- `[RESULT]` one completed evaluation with parameter values and objective value
- `[HEARTBEAT]` periodic liveness messages

## Expected artifacts

Artifacts are written under:

```text
artifacts/ackley_bomcp_benchmark/campaign_<campaign_id>/
```

Files:

- `campaign_ref.json` — includes `campaign_id`, `campaign_name`, marker, and nonce
- `campaign_id.txt` — plain campaign id for easy extraction
- `evaluations.jsonl` — one row per evaluated candidate
- `evaluations.csv` — flattened table for easy review/export
- `run.log` — detailed log file
- `campaign_manifest.json` at workspace root — package paths, run entrypoint, latest artifact dir, latest campaign id

The evaluation rows include at least:

- `evaluation_index`
- `parameter_values` (`x_1..x_6`)
- `objective_values.surface_response`
- `status`
- `failure_reason`
- `raw_response`

## Stop-file behavior

Before each new suggestion request, the script checks for the stop file path from `--stop-file`.

Default stop file:

```text
STOP
```

When the file exists, the script:

1. prints an `[EVENT]` line,
2. deletes the stop file,
3. exits through normal shutdown,
4. pauses the campaign if it is still running.

Resume command after a stop-file exit:

```bash
PYTHONUNBUFFERED=1 python run_ackley_bomcp_benchmark.py --campaign-id <campaign_id> --poll-s 180 --heartbeat-s 1800 --stop-file STOP
```

## How to identify the owned campaign

Use either of these:

- the `[EVENT]` line with `"kind": "campaign_created"`
- `artifacts/ackley_bomcp_benchmark/campaign_<campaign_id>/campaign_ref.json`
- `artifacts/ackley_bomcp_benchmark/campaign_<campaign_id>/campaign_id.txt`
- `campaign_manifest.json` at workspace root

The owned campaign name always contains:

```text
akg-eval-88fef1120e594d599505287c7dd8ba7f
```
