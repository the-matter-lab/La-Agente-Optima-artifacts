# HOW TO EXECUTE: Direct Arylation Yield BO-MCP Campaign

## Overview

Bayesian optimization of direct-arylation reaction yield over a 5-parameter
fully-crossed search space (1,728 combinations).  The objective is a
table-lookup oracle accessed via `DIRECT_ARYLATION_API_URL`.

- **Campaign marker**: `akg-eval-4177a21e5ec54adb9b46a50c81885888`
- **Budget**: exactly 60 attempted oracle evaluations per invocation
- **Objective**: maximize `yield` (percent)

## Search Space

| Parameter       | Type        | Values |
|-----------------|-------------|--------|
| `base`          | categorical | Potassium acetate, Potassium pivalate, Cesium acetate, Cesium pivalate |
| `ligand`        | categorical | BrettPhos, Di-tert-butylphenylphosphine, (t-Bu)PhCPhos, Tricyclohexylphosphine, PPh3, XPhos, P(2-furyl)3, Methyldiphenylphosphine, 1268824-69-6, JackiePhos, SCHEMBL15068049, Me2PPh |
| `solvent`       | categorical | DMAc, Butyornitrile, Butyl Ester, p-Xylene |
| `concentration` | discrete    | 0.057, 0.1, 0.153 |
| `temperature_c` | discrete    | 90, 105, 120 |

## Environment Variables

| Variable                  | Required | Description |
|---------------------------|----------|-------------|
| `BO_MCP_API_URL`          | **yes**  | BO-MCP REST API base URL |
| `BO_MCP_API_KEY`          | **yes**  | BO-MCP API key |
| `DIRECT_ARYLATION_API_URL`| **yes**  | Yield oracle base URL |

## Execution Command

```bash
# First run (creates a new campaign):
PYTHONPATH=/app python run_direct_arylation_benchmark.py

# Resume an existing campaign:
PYTHONPATH=/app python run_direct_arylation_benchmark.py --campaign-id <CAMPAIGN_ID>

# Custom budget (default 60):
PYTHONPATH=/app python run_direct_arylation_benchmark.py --max-attempts 30
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--campaign-id` | (none) | Existing campaign ID to resume |
| `--max-attempts` | 60 | Hard cap on oracle calls this invocation |
| `--poll-s` | 180 | Seconds between iterations |
| `--heartbeat-s` | 1800 | Seconds between heartbeat lines |
| `--stop-file` | `STOP` | Path to stop-marker file in CWD |
| `--results-jsonl` | `results.jsonl` | Path for results JSONL output |

## Stop / Resume Semantics

- **Stop**: create a file named `STOP` (or your `--stop-file` path) in the
  working directory.  The script checks for it at the top of each iteration
  (before generating a suggestion), deletes it, and exits through the normal
  shutdown path — pausing the campaign.
- **Resume**: re-run the same command with `--campaign-id <ID>`.  The script
  detects the campaign status (paused → resume, completed → reopen) and
  continues from where it left off.
- **Never terminate**: the script pauses at shutdown so you can always resume.
  Only terminate if you are certain the campaign is done forever.

## Output / Artifacts

### Tagged stdout lines

| Tag | Meaning |
|-----|---------|
| `[EVENT]` | State changes: create, resume, iteration info, pause |
| `[ALERT]` | Failures: oracle errors, submission rejections |
| `[RESULT]` | Per-evaluation yield and final report |
| `[HEARTBEAT]` | Periodic liveness ping |

### Files

| File | Content |
|------|---------|
| `results.jsonl` | Append-only JSONL of all evaluated candidates with statuses and yields |
| `campaign_manifest.json` | Package module paths, entrypoint path, campaign ID |

### Final Report

At the end of the run, the script prints:
- Best reaction conditions (all 5 parameters)
- Best measured yield
- Numbers of successful and attempted evaluations
- All evaluated candidates with statuses and objective values

## Package Structure

```
direct_arylation_benchmark/
├── __init__.py          # Package marker
├── search_space.py      # Parameter definitions (1,728 combinations)
├── intake.py            # Campaign intake construction
├── evaluator.py         # Oracle evaluation via DIRECT_ARYLATION_API_URL
├── objective.py         # ResultLedger: accumulation, reporting, JSONL
└── campaign.py          # BO-MCP loop orchestrator (campaign-agnostic)
run_direct_arylation_benchmark.py  # CLI entrypoint
campaign_manifest.json             # Written at end of run
HOW_TO_EXECUTE_CAMPAIGN.md         # This file
```

## Campaign Design Decisions

- **Backend**: `auto` — BO-MCP selects the best available backend.
- **Acquisition**: `expected_improvement` — standard for noise-free table lookups.
- **Initial design**: 12 Sobol points for space-filling warmup.
- **Batch size**: 1 (fully sequential).
- **No `max_iterations` / `max_observations`** in the immutable intake — the
  CLI `--max-attempts` budget controls this invocation only, so resume works.
- **Failed evaluations**: rejected from BO-MCP (via `update_suggestion_status`)
  so they don't pollute the surrogate model; the attempt still counts against
  the budget.