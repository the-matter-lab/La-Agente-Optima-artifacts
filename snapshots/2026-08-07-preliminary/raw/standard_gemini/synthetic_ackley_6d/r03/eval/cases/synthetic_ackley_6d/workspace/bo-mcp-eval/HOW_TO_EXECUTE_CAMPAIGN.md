# HOW TO EXECUTE CAMPAIGN: Ackley 6D Synthetic Surface Optimization

- Cache-buster nonce: `54354cdc-4da6-4419-86a6-f4560fc0efbe`
- Ownership marker: `akg-eval-43dcff3d628d4a86ba717e0455386a93`

## Chosen campaign settings for this invocation
- backend: `botorch`
- random seed: `20260730`
- initialization strategy: BO-MCP/BoTorch Sobol-style space-filling warm start
- initial design size: `12`
- batch schedule: sequential `batch_size=1`
- acquisition method: `expected_improvement_nonlog`
- budget: exactly `60` attempted objective evaluations

## Required environment
- `BO_MCP_API_URL`
- `BO_MCP_API_KEY`
- `PYTHONPATH=/app`

## Start a new campaign
```bash
PYTHONUNBUFFERED=1 PYTHONPATH=/app python run_ackley_6d.py   --name "Ackley 6D Optimization akg-eval-43dcff3d628d4a86ba717e0455386a93"   --seed 20260730   --init-size 12   --backend botorch   --poll-s 0   --heartbeat-s 30   --artifact-dir artifacts
```

## Resume an existing owned campaign
```bash
PYTHONUNBUFFERED=1 PYTHONPATH=/app python run_ackley_6d.py   --campaign-id <campaign_id>   --poll-s 0   --heartbeat-s 30   --artifact-dir artifacts
```

Only resume campaigns whose BO-MCP campaign name contains the ownership marker.

## Monitoring tags
- `[EVENT]` lifecycle / loop state
- `[ALERT]` failures or duplicate-suggestion rejections
- `[RESULT]` successful objective evaluations
- `[HEARTBEAT]` liveness + counts

## Stop file
Create `STOP` in the workspace root to pause the campaign gracefully. The script removes the stop file, pauses the BO-MCP campaign, and exits.

## Artifacts
Primary artifact written by the script:
- `artifacts/results_history.json`

Each row includes:
- `evaluation_index`
- `parameter_values` with `x_1`..`x_6`
- `objective_values.surface_response`
- `status`
- `failure_reason`
- `raw_response`

At completion the script prints exactly one line in this format:
```text
BO_MCP_CAMPAIGN_ID=<campaign_id>
```
