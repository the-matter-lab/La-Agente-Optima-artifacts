# HOW TO EXECUTE CAMPAIGN

This document describes how to run and validate the direct arylation Bayesian Optimization campaign using the BO-MCP architecture.

## Campaign Details
- **Campaign Ownership Marker**: `akg-eval-c3e0d2ed3ebe4370ba327899b1a83fed`
- **User Cache-Buster Nonce**: `bc27a984-bcee-47bd-8b53-bbd5d03f3b3f`
- **Objective**: Maximize `yield` (percent)
- **Budget**: Exactly 60 attempted evaluations

## Environment Requirements
The following environment variables must be set before running the script:
- `BO_MCP_API_URL`: Base URL of the BO-MCP REST API (e.g., `http://api:8000`).
- `BO_MCP_API_KEY`: API key for authenticating with the BO-MCP REST API.
- `DIRECT_ARYLATION_API_URL`: Base URL of the direct arylation reaction oracle API.

## Execution Commands

### 1. Start a New Campaign
To start a brand new campaign, run:
```bash
PYTHONPATH=/app python run_direct_arylation.py --poll-s 180 --max-attempts 60
```

### 2. Resume an Existing Campaign
If the campaign is paused or interrupted, you can resume it by passing the `--campaign-id` argument:
```bash
PYTHONPATH=/app python run_direct_arylation.py --campaign-id <CAMPAIGN_ID> --poll-s 180 --max-attempts 60
```

## Stop File Behavior
To stop the campaign gracefully at the top of the next iteration, create a file named `STOP` in the current working directory:
```bash
touch STOP
```
The script checks for this file at the start of each iteration. When detected, it will:
1. Print `[EVENT] Stop file 'STOP' detected. Shutting down gracefully.`
2. Delete the `STOP` file so subsequent runs are not immediately stopped.
3. Pause the campaign on the BO-MCP server.
4. Exit cleanly.

## Output Tags and Monitoring
The script prints unbuffered tagged lines to `stdout` for easy monitoring:
- `[EVENT]`: State changes (e.g., campaign creation, suggestion generation, graceful shutdown).
- `[ALERT]`: Failures, errors, and stop conditions.
- `[RESULT]`: Full per-experiment analysis (e.g., candidate parameters and measured yield).
- `[HEARTBEAT]`: Liveness indicator printed periodically.

## Artifacts
- **Local Results File**: `direct_arylation_results.json` (default, configurable via `--results-file`).
  This file is an append-only JSON array containing one record per attempt. Each record uses the standardized format:
  ```json
  {
    "parameter_values": {
      "base": "Potassium acetate",
      "ligand": "(t-Bu)PhCPhos",
      "solvent": "DMAc",
      "concentration": 0.1,
      "temperature_c": 105.0
    },
    "objective_values": {
      "yield": 42.5
    },
    "status": "success",
    "suggestion_id": "sug-..."
  }
  ```
  For failed attempts, `objective_values` is `null` and `status` is `"failed"`.
