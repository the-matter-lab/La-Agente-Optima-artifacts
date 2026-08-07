# How to Execute the Direct Arylation BO Campaign

## Overview

This script runs a Bayesian optimization campaign via the BO-MCP service to maximize direct arylation reaction yield over a fully crossed search space of 1,728 reactions. The budget is **exactly 60 attempted evaluations**.

## Prerequisites

### Required Environment Variables

| Variable | Description |
|---|---|
| `BO_MCP_API_URL` | Base URL of the BO-MCP REST API (e.g. `http://api:8000`) |
| `BO_MCP_API_KEY` | API key for BO-MCP authentication |
| `DIRECT_ARYLATION_API_URL` | Base URL of the direct arylation oracle (e.g. `http://oracle:5000`) |

### Python Dependencies

The script uses packages available in the container's `uv` environment. No additional installs are needed.

## Running the Campaign

### First Run (New Campaign)

```bash
PYTHONPATH=/app python run_direct_arylation_bo.py
```

### Resume a Paused Campaign

```bash
PYTHONPATH=/app python run_direct_arylation_bo.py --campaign-id <CAMPAIGN_ID>
```

### Stop a Running Campaign

Create the stop file (default: `STOP` in the working directory):

```bash
touch STOP
```

The campaign will detect the file at the top of the next loop iteration, pause the campaign on the BO-MCP server, delete the stop file, and exit. Resume later with `--campaign-id`.

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--campaign-id` | None | Existing campaign ID to resume |
| `--stop-file` | `STOP` | Path to stop-file marker |
| `--poll-s` | 180 | Seconds between loop iterations |
| `--heartbeat-s` | 1800 | Seconds between heartbeat log lines |

## Tagged Output Lines

The script prints tagged unbuffered lines to stdout for monitoring:

| Tag | Meaning |
|---|---|
| `[EVENT]` | State changes (campaign created, paused, loop ended, etc.) |
| `[ALERT]` | Failures and stop conditions |
| `[RESULT]` | Per-experiment yield and final summary |
| `[HEARTBEAT]` | Liveness check with progress stats |

All other output goes to the run log on disk.

## Artifacts

All artifacts are written to `./artifacts/`:

| File | Description |
|---|---|
| `campaign_id.txt` | The BO-MCP campaign ID |
| `evaluations.jsonl` | Append-only record of every attempted evaluation |
| `summary.json` | Final summary with best yield, best conditions, all records |
| `diagnostics.json` | BO-MCP campaign diagnostics (fetched at end) |

## Campaign ID

The campaign ID is printed as:
```
[RESULT] BO_MCP_CAMPAIGN_ID=<campaign_id>
```

It is also stored in `artifacts/campaign_id.txt`.

## Output Reporting

After execution, the following are available in `artifacts/summary.json`:

- **best reaction conditions** — `best_conditions` field
- **best measured yield** — `best_yield` field (percent)
- **number of successful evaluations** — `n_successful` field
- **number of attempted evaluations** — `n_attempted` field
- **all evaluated candidates** — `all_records` field, each with:
  - `parameter_values` — the five lowercase parameter names and values
  - `objective_values` — `{"yield": <value>}` for successes, `null` for failures
  - `status` — `"success"` or `"failed"`

## Campaign Ownership Marker

Every campaign created by this script includes the marker `akg-eval-a9d88670aa904fcb95a87e64a470e6bf` in its name.

## Resume Behavior

- A **paused** campaign is resumed with `action="resume"`.
- A **completed** campaign is reopened with `action="reopen"`.
- The loop re-derives its position from the BO-MCP server — no local state files are read for loop decisions.
- The budget (60 attempts) is enforced per invocation; a resumed run starts a fresh 60-attempt budget.

## Search Space

| Parameter | Type | Values |
|---|---|---|
| `base` | categorical | Potassium acetate, Potassium pivalate, Cesium acetate, Cesium pivalate |
| `ligand` | categorical | BrettPhos, Di-tert-butylphenylphosphine, (t-Bu)PhCPhos, Tricyclohexylphosphine, PPh3, XPhos, P(2-furyl)3, Methyldiphenylphosphine, 1268824-69-6, JackiePhos, SCHEMBL15068049, Me2PPh |
| `solvent` | categorical | DMAc, Butyornitrile, Butyl Ester, p-Xylene |
| `concentration` | discrete | 0.057, 0.1, 0.153 |
| `temperature_c` | discrete | 90, 105, 120 |

## Objective

- **Name**: `yield`
- **Direction**: `maximize`
- **Unit**: `percent`
