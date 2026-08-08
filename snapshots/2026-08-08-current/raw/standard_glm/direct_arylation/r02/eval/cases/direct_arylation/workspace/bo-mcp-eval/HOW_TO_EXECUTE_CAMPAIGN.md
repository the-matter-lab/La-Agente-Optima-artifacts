# How to Execute the Direct Arylation BO Campaign

## Overview

This campaign optimizes direct arylation reaction yield over a fully crossed
search space of 1,728 reactions (4 bases × 12 ligands × 4 solvents × 3
concentrations × 3 temperatures) using Bayesian optimization via the BO-MCP
service. The budget is **exactly 60 attempted objective evaluations**.

## Campaign Name Template

Every BO-MCP campaign created by this script includes the required marker:

```
direct-arylation-akg-eval-d9613e26762c4c47a426799e86b370f2-<label>
```

## Required Environment Variables

| Variable | Description |
|---|---|
| `BO_MCP_API_URL` | BO-MCP REST API base URL (e.g. `http://api:8000`) |
| `BO_MCP_API_KEY` | BO-MCP API key |
| `DIRECT_ARYLATION_API_URL` | Oracle base URL (e.g. `http://direct-arylation-oracle:8000`) |

## Execution Commands

### Fresh Run (New Campaign)

```bash
cd /app/outputs/cells/direct_arylation_standard_glm_r02/eval/cases/direct_arylation/workspace/bo-mcp-eval
uv run python run_direct_arylation.py --max-attempts 60 --artifact-dir ./artifacts
```

### Resume an Existing Campaign

```bash
uv run python run_direct_arylation.py --campaign-id <CAMPAIGN_ID> --max-attempts 60 --artifact-dir ./artifacts
```

The script will automatically:
- Resume a **paused** campaign
- Reopen a **completed** campaign
- Continue from the server's recorded progress

### Stop a Running Campaign

Create the stop file in the working directory:

```bash
touch STOP
```

The script checks for `STOP` at the top of each loop iteration (before
generating a new suggestion). When detected, it:
1. Prints `[EVENT] Stop file detected`
2. Deletes the stop file (so a resume won't immediately stop again)
3. Pauses the campaign on the BO-MCP server
4. Exits cleanly

**Important:** The stop file is checked *before* suggestion generation, never
between evaluation and result submission. This ensures no evaluated result is
lost.

## Monitor-Friendly Output Tags

The script prints unbuffered tagged lines for the monitor:

| Tag | Meaning |
|---|---|
| `[EVENT]` | State changes, campaign lifecycle, iteration progress |
| `[ALERT]` | Failures, errors, non-2xx oracle responses |
| `[RESULT]` | Full per-experiment analysis: attempt number, yield, parameters |
| `[HEARTBEAT]` | Liveness signal (every `--heartbeat-s` seconds, default 1800) |

The final line of output is always:

```
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

## Outputs and Artifacts

All artifacts are written to the `--artifact-dir` (default: `./artifacts`):

| File | Description |
|---|---|
| `evaluation_log.jsonl` | One JSON record per attempt (append-only) |
| `diagnostics.json` | Campaign diagnostics from BO-MCP (fetched at end) |

### evaluation_log.jsonl Record Format

Each line is a JSON object:

```json
{
  "attempt_index": 1,
  "timestamp": "2026-07-30T17:30:00.000000+00:00",
  "parameter_values": {
    "base": "Potassium acetate",
    "ligand": "BrettPhos",
    "solvent": "DMAc",
    "concentration": 0.1,
    "temperature_c": 105
  "status": "success",
  "objective_values": {"yield": 42.5},
  "suggestion_id": "abc123"
}
```

For **failed** attempts:

```json
{
  "attempt_index": 2,
  "timestamp": "...",
  "parameter_values": {...},
  "status": "failed",
  "error": "HTTP 500: internal error",
  "suggestion_id": "def456"
}
```

## Campaign Design

| Aspect | Choice | Rationale |
|---|---|---|
| Parameter encoding | 3 categorical + 2 discrete numeric | Categorical preserves spelling; discrete numeric sends JSON numbers to oracle |
| Batch size | 1 | Sequential evaluation; each observation informs the next |
| Initial design | 8 Sobol points | Sparse warmup for 5-dim mixed space |
| Acquisition | Expected Improvement | Classic EI for maximization with small budget |
| Backend | `auto` | Server picks the best available backend |
| Budget control | CLI `--max-attempts` | Not in intake (immutable); allows resume/reopen |

## CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--campaign-id` | None | Resume an existing campaign |
| `--max-attempts` | 60 | Per-invocation evaluation budget |
| `--artifact-dir` | `./artifacts` | Output directory |
| `--stop-file` | `STOP` | Graceful-pause trigger file |
| `--poll-s` | 5.0 | Sleep between iterations (seconds) |
| `--heartbeat-s` | 1800.0 | Heartbeat interval (seconds) |

## After Execution

The main agent should report:
1. **Best conditions** (parameter values of the highest-yield evaluation)
2. **Best measured yield** (the highest yield value observed)
3. **Successful/attempted counts** (e.g. 58/60)
4. **All evaluated candidates, statuses, and objective values** (from `evaluation_log.jsonl`)
5. **Exactly one line:** `BO_MCP_CAMPAIGN_ID=<campaign_id>`
