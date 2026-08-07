# How to Execute the Direct Arylation BO Campaign

## Prerequisites

### Required Environment Variables

```bash
export BO_MCP_API_URL="http://api:8000"          # BO-MCP REST API base URL
export BO_MCP_API_KEY="[REDACTED]"              # BO-MCP API key
export DIRECT_ARYLATION_API_URL="http://oracle:8080"  # Oracle API base URL
```

## First Run (Create New Campaign)

```bash
cd /app/outputs/cells/direct_arylation_standard_nemotron_r02/eval/cases/direct_arylation/workspace/bo-mcp-eval

python run_direct_arylation.py \
    --max-evaluations 60 \
    --batch-size 1 \
    --artifacts-dir artifacts
```

This will:
1. Create a new BO-MCP campaign with the required marker
2. Run up to 60 oracle evaluations (or until BO-MCP signals convergence)
3. Write artifacts to `artifacts/`
4. Print final summary including `BO_MCP_CAMPAIGN_ID=<id>`

## Resume a Paused Campaign

```bash
python run_direct_arylation.py \
    --campaign-id <CAMPAIGN_ID_FROM_FIRST_RUN> \
    --max-evaluations 60 \
    --artifacts-dir artifacts
```

The script automatically pauses the campaign at the end of each invocation. Resume with the same `--campaign-id`.

## Stop a Running Campaign

Create a `STOP` file in the working directory:

```bash
touch STOP
```

The campaign will:
1. Detect the file at the start of the next iteration
2. Delete the `STOP` file (so resume isn't blocked)
3. Pause the campaign on the server
4. Exit cleanly with final report

## Output Artifacts

All artifacts are written to `--artifacts-dir` (default `artifacts/`):

| File | Description |
|------|-------------|
| `campaign_summary.json` | Machine-readable summary with all evaluations |
| `campaign_report.txt` | Human-readable final report |

## Stdout Tags

The script emits tagged lines for monitoring:

| Tag | Meaning |
|-----|---------|
| `[EVENT]` | State changes (campaign create, suggestion generated, pause, etc.) |
| `[RESULT]` | Successful oracle evaluation with yield value |
| `[ALERT]` | Failures (oracle error, submission rejected, etc.) |
| `[HEARTBEAT]` | Periodic liveness (every 5 evaluations by default) |

## Campaign Budget

- **Hard cap**: 60 total oracle evaluations (enforced by `max_observations=60` in intake + CLI `--max-evaluations`)
- Each oracle request = 1 evaluation attempt
- Failed evaluations count toward the 60-attempt budget
- The campaign stops when: 60 attempts reached, BO-MPC signals convergence, or `STOP` file detected

## Expected Final Output

```
============================================================
CAMPAIGN COMPLETE
============================================================
Campaign ID: camp_abc123...
Objective: yield (maximize, percent)
Total attempted: 60
Successful: 58
Failed: 2
Best yield: 94.52%
Best conditions:
  base: Cesium pivalate
  ligand: XPhos
  solvent: DMAc
  concentration: 0.100
  temperature_c: 120
============================================================
BO_MCP_CAMPAIGN_ID=camp_abc123...
```

The `BO_MCP_CAMPAIGN_ID` line is the required marker for the final user response.