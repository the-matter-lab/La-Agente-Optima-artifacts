# How to Execute the Direct Arylation BO-MCP Campaign

## Overview

This campaign optimizes the measured yield of a direct arylation reaction over a fixed fully crossed search space of **1,728 measured reactions** using Bayesian Optimization via BO-MCP. The campaign uses **oracle queries only** (HTTP POST to `${DIRECT_ARYLATION_API_URL}/v1/evaluate`) with a budget of **exactly 60 total attempted oracle evaluations (including failures) across the campaign lifetime**.

## Prerequisites

### Required Environment Variables

```bash
export BO_MCP_API_URL="http://api:8000"          # BO-MCP REST API base URL
export BO_MCP_API_KEY="[REDACTED]"         # BO-MCP API key
export DIRECT_ARYLATION_API_URL="http://oracle:8080"  # Oracle API for yield evaluations
```

### Required Marker

Every campaign created by this invocation **must** include the marker:
```
akg-eval-0c360b08e6684de0b0ed04f50bde3b2c
```

This marker is embedded in the campaign name and validated on resume.

### Cache-Buster Nonce

```
16e7e684-7bf5-4a9b-af93-fae14403be06
```

Used in campaign name and documentation for traceability.

## Quick Start

## Quick Start

```bash
# From the workspace directory
cd /app/outputs/cells/direct_arylation_standard_nemotron_r03/eval/cases/direct_arylation/workspace/bo-mcp-eval

# Run the campaign (creates new campaign)
python run_direct_arylation.py

# Or with custom parameters
python run_direct_arylation.py --max-attempts 60 --poll-s 180 --heartbeat-s 1800
```

**No `PYTHONPATH` required** — the entry point script automatically adds `/app` to `sys.path` for the `domains` package.
# From the workspace directory
cd /app/outputs/cells/direct_arylation_standard_nemotron_r03/eval/cases/direct_arylation/workspace/bo-mcp-eval

# Run the campaign (creates new campaign)
python run_direct_arylation.py

# Or with custom parameters
python run_direct_arylation.py --max-attempts 60 --poll-s 180 --heartbeat-s 1800
```

## Resume / Continue

If the run is interrupted (Ctrl+C, stop file, crash), resume by re-running with the campaign ID:

```bash
# Get the campaign ID from the previous run's output (BO_MCP_CAMPAIGN_ID=...)
python run_direct_arylation.py --campaign-id <CAMPAIGN_ID>
```

The script will:
1. Verify the campaign has the required marker
2. Load existing attempt history from the local artifact (`artifacts/<campaign_id>/attempts.jsonl`)
3. Continue the optimization loop, enforcing the **total 60-attempt budget across all runs**
4. Append new attempts to the same artifact file

**Key budget semantics**: `--max-attempts` bounds the **campaign lifetime total** (not per invocation). The artifact file `artifacts/<campaign_id>/attempts.jsonl` is the source of truth for attempted evaluations. Resuming does not reset the budget.

## Stop File (Graceful Pause)

Create a `STOP` file in the working directory to pause the campaign gracefully:

```bash
touch STOP
```

The campaign will:
- Detect the stop file at the start of the next loop iteration
- Submit any pending results first
- Pause the campaign on the BO-MCP server
- Delete the stop file
- Exit cleanly

To continue after a stop, re-run with `--campaign-id`.

## Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--campaign-id` | (none) | Resume existing campaign by ID |
| `--max-attempts` | 60 | **Maximum total oracle evaluation attempts (including failures) for the campaign lifetime** |
| `--poll-s` | 180 | Polling interval for `next_action()` (seconds, 120–300 recommended) |
| `--heartbeat-s` | 1800 | Heartbeat logging interval (seconds) |
| `--stop-file` | `STOP` | Path to stop file |

## Output Tags (Monitoring)

The script emits tagged lines to stdout for monitoring:

| Tag | Meaning |
|-----|---------|
| `[EVENT]` | State changes, campaign start/stop, loop decisions |
| `[ALERT]` | Failures, errors, rejected suggestions, duplicate results |
| `[RESULT]` | Successful oracle evaluations with yield values |
| `[HEARTBEAT]` | Periodic liveness signal |

Example output:
```
[EVENT] Starting Direct Arylation BO campaign (marker=akg-eval-0c360b08e6684de0b0ed04f50bde3b2c, nonce=16e7e684-7bf5-4a9b-af93-fae14403be06)
[EVENT] Created new campaign: camp_abc123def456
[EVENT] Server decision: action=bo_generate_suggestions, reason=initial_design, status=running, iter=0, results=0
[EVENT] Received suggestion sug_xyz789: {'base': 'Potassium acetate', 'ligand': 'BrettPhos', 'solvent': 'DMAc', 'concentration': 0.1, 'temperature_c': 90}
[EVENT] Evaluating candidate via oracle API...
[RESULT] Yield: 78.95% | base=Potassium acetate, ligand=BrettPhos, solvent=DMAc, conc=0.1M, temp=90°C
[EVENT] Submitted 1 results to BO-MCP
[HEARTBEAT] Campaign camp_abc123def456 alive; attempted=5/60
...
[EVENT] Total attempt budget exhausted (60)
[ALERT] Budget reached; pausing campaign
[EVENT] Campaign paused for resumption

=== CAMPAIGN REPORT: camp_abc123def456 ===
Total attempted evaluations: 60
Successful:                  58
Failed:                      2
Best yield: 92.34%
  Conditions: base=Cesium pivalate, ligand=JackiePhos, solvent=Butyornitrile, conc=0.153M, temp=120°C
...
BO_MCP_CAMPAIGN_ID=camp_abc123def456
```

## Final Report

At completion, the script prints:
1. Full campaign report with **all attempted candidates from the artifact** (including failed attempts and attempts from prior runs)
2. Summary statistics (best/worst/mean yield)
3. **Required final line**: `BO_MCP_CAMPAIGN_ID=<campaign_id>`

## Search Space Definition

| Parameter | Type | Values (exact) |
|-----------|------|----------------|
| `base` | Categorical (4) | Potassium acetate, Potassium pivalate, Cesium acetate, Cesium pivalate |
| `ligand` | Categorical (12) | BrettPhos, Di-tert-butylphenylphosphine, (t-Bu)PhCPhos, Tricyclohexylphosphine, PPh3, XPhos, P(2-furyl)3, Methyldiphenylphosphine, 1268824-69-6, JackiePhos, SCHEMBL15068049, Me2PPh |
| `solvent` | Categorical (4) | DMAc, Butyornitrile, Butyl Ester, p-Xylene |
| `concentration` | Discrete numeric (3) | 0.057, 0.1, 0.153 |
| `temperature_c` | Discrete numeric (3) | 90, 105, 120 |

**Total combinations**: 4 × 12 × 4 × 3 × 3 = 1,728

**Note**: `concentration` and `temperature_c` are modeled as **discrete numeric** parameters in the BO-MCP intake (type `discrete` with explicit `values` arrays), not categorical strings.

## Oracle API Contract

**Endpoint**: `POST ${DIRECT_ARYLATION_API_URL}/v1/evaluate`

**Request body** (exact field names and values):
```json
{
  "base": "Potassium acetate",
  "ligand": "BrettPhos",
  "solvent": "DMAc",
  "concentration": 0.1,
  "temperature_c": 90
}
```

**Response** (success):
```json
{"yield": 78.95}
```

**Non-2xx** = failed evaluation (counts toward 60-attempt budget)

## Campaign Configuration (BO-MCP Intake)

- **Objective**: `yield` (maximize, unit: percent)
- **Backend**: `auto` (BoTorch or BayBE)
- **Acquisition**: `auto`
- **Batch size**: 1
- **Initial design**: 10 (Sobol/LHS warmup)
- **Max observations**: 60 (hard cap on successful results stored in BO-MCP)
- **Random seed**: 42 (reproducible initial design)

## File Structure

```
workspace/
├── run_direct_arylation.py          # Entry point
├── direct_arylation_campaign/       # Campaign package
│   ├── __init__.py
│   ├── search_space.py              # Parameter definitions & validation
│   ├── intake.py                    # BO-MCP campaign intake builder
│   ├── evaluator.py                 # Oracle API evaluation logic
│   ├── reporter.py                  # Result extraction & reporting
│   ├── attempt_tracking.py          # Local attempt artifact (JSONL)
│   └── campaign.py                  # Orchestration loop
├── HOW_TO_EXECUTE_CAMPAIGN.md       # This file
├── campaign_manifest.json           # Package manifest
├── STOP                             # Stop file (created by user to pause)
└── artifacts/                       # Attempt tracking artifacts (per campaign)
    └── <campaign_id>/
        └── attempts.jsonl           # All 60 attempts (success + failure)
```

## Attempt Tracking Artifact

The file `artifacts/<campaign_id>/attempts.jsonl` is an append-only JSONL log of **all oracle evaluation attempts** (successful and failed). Each line is a JSON object:

```json
{
  "suggestion_id": "uuid-from-bo-mcp",
  "candidate": {"base": "...", "ligand": "...", "solvent": "...", "concentration": 0.1, "temperature_c": 90},
  "yield": 78.95,
  "status": "success",
  "error": null,
  "elapsed_s": 1.23,
  "timestamp": 1234567890.123
}
```

**Purpose**: 
- Enforces the 60-attempt budget across resumes (source of truth for `count_attempts()`)
- Provides complete history for final reporting (including failures)
- Survives process restarts and campaign pauses

**Do not delete or modify this file** — it is the campaign's budget ledger.

## Troubleshooting

### Campaign won't start
- Verify `BO_MCP_API_URL`, `BO_MCP_API_KEY`, `DIRECT_ARYLATION_API_URL` are set
- Check BO-MCP server health: `curl ${BO_MCP_API_URL}/health`
- Check oracle API: `curl ${DIRECT_ARYLATION_API_URL}/health`

### Oracle evaluations failing
- Verify oracle API accepts the exact parameter values (case-sensitive, spelling)
- Check network connectivity and timeouts
- Failed evaluations count toward the 60-attempt budget

### Resume not working
- Ensure campaign ID has the marker `akg-eval-0c360b08e6684de0b0ed04f50bde3b2c`
- Campaign must be in `paused` or `running` state (not `terminated`)
- Use `action="reopen"` via lifecycle API if campaign shows `completed`
- Check `artifacts/<campaign_id>/attempts.jsonl` exists and is readable

### Budget confusion
- `--max-attempts` bounds the **campaign lifetime total** (not per invocation)
- The artifact `artifacts/<campaign_id>/attempts.jsonl` is the budget ledger
- BO-MCP `max_observations=60` caps successful results stored in BO-MCP
- Server-side `next_action()` will return `budget_exceeded` when 60 total results exist

## Logfire Instrumentation

The script configures Logfire for request tracing. Set `LOGFIRE_TOKEN` if you want to export traces.

## Validation

Before full run, do a smoke test (1 iteration):

```bash
python run_direct_arylation.py --max-attempts 1 --poll-s 10 --heartbeat-s 10
```

Verify:
- `[EVENT]` campaign created
- `[EVENT]` suggestion generated
- `[RESULT]` or `[ALERT]` from oracle
- `[EVENT]` results submitted
- Final report prints `BO_MCP_CAMPAIGN_ID=...`
- `artifacts/<campaign_id>/attempts.jsonl` created with 1 entry