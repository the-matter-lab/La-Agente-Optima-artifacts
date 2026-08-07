# How to execute the Ackley 6D BO-MCP campaign

## Files
- Entry point: `run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py`
- Package: `ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068/`
- Manifest: `campaign_manifest.json`

## Required environment
Set these before running:
- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`

The script imports BO-MCP and Grafico modules from the repository checkout. In this container, local validation used:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py ...
```

That avoids the local `uv run` editable-build issue on a read-only `/app` mount.

## Benchmark behavior
- Objective: maximize `surface_response`
- Search space: continuous `x_1`..`x_6` in `[0, 1]`
- Mapping: `z_i = -40 + 80*x_i`
- Surface: deterministic normalized Ackley benchmark
- Total budget: exactly `60` BO-MCP observations for the full benchmark
- Duplicate candidate protection: exact repeated points are rejected before evaluation
- Campaign ownership marker enforced in campaign names: `akg-eval-6c34bf90d0b945098371e25f43d3e068`

Chosen BO settings in the script:
- backend: `botorch`
- batch size: `1`
- initial design size: `9`
- acquisition: `upper_confidence_bound`
- acquisition beta: `0.2`
- random seed default: `271828`

## Fresh full run
From the workspace root:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py \
  --artifact-dir artifacts_akg-eval-6c34bf90d0b945098371e25f43d3e068
```

## Reuse the validated smoke-test campaign
A one-attempt smoke test already created and paused a compatible campaign:
- campaign id: `f4829707-af29-475b-93c2-ce9a28d9bdad`
- artifact dir: `artifacts_akg-eval-6c34bf90d0b945098371e25f43d3e068_smoke2`

Resume it from the workspace root with:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py \
  --campaign-id f4829707-af29-475b-93c2-ce9a28d9bdad \
  --artifact-dir artifacts_akg-eval-6c34bf90d0b945098371e25f43d3e068_smoke2
```

That campaign already contains 1 submitted evaluation, so completing it should add the remaining 59 successful evaluations unless an unexpected failure occurs.

## Optional bounded invocation
Use `--max-attempts-this-run` to stop after a smaller number of attempts while keeping the BO-MCP campaign resumable:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py \
  --campaign-label partial \
  --max-attempts-this-run 5
```

## Stop/resume behavior
- The script checks `--stop-file` at the top of each loop iteration.
- Default stop file: `STOP` in the current working directory.
- To request a clean stop, create that file while the run is active.
- The script deletes the stop file when it notices it, then exits normally.
- At the end of an invocation, the script pauses the campaign when it is still running.

## Tagged stdout lines
The entry point is designed for monitors that forward selected stdout lines:
- `[EVENT]` lifecycle changes, budget stop, pause/resume, clean shutdown
- `[ALERT]` duplicate suggestions, evaluation failures, submission failures
- `[RESULT]` one line per attempted evaluation with coordinates and objective value
- `[HEARTBEAT]` periodic liveness update

Everything else is written to disk artifacts.

## Artifacts written under `--artifact-dir`
- `results.jsonl`: append-only per-evaluation artifact with status and failure reason
- `summary.json`: current best point and full record list
- `run.log`: detailed execution log
- `diagnostics.json`: BO-MCP diagnostics snapshot
- `campaign_export.csv`: BO-MCP export snapshot

## Validation checklist after a run
1. Confirm stdout contains `[RESULT]` lines and a final `[EVENT] Run complete ...` line.
2. Read `summary.json` for:
   - `best_parameter_values`
   - `best_raw_response`
   - `best_surface_response`
   - `attempted_evaluations`
   - `successful_evaluations`
3. Read `results.jsonl` to build the full evaluated-candidates table.
4. Report the final campaign id exactly once as:

```text
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

## Resume command template
If a run is interrupted, resume with:

```bash
PYTHONPATH=/app python run_ackley6d_akg_eval_6c34bf90d0b945098371e25f43d3e068.py \
  --campaign-id <campaign_id> \
  --artifact-dir <artifact_dir>
```
