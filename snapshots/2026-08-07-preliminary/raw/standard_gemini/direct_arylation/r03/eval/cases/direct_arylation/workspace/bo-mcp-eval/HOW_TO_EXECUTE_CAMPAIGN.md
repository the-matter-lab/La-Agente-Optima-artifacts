# How to Execute the Direct Arylation BO-MCP Campaign

This document explains how to run, monitor, and manage the Bayesian Optimization campaign for the direct arylation benchmark.

## Workspace Files

- **Run Entrypoint**: `run_direct_arylation.py` (workspace-relative path)
- **Campaign Package**: `direct_arylation/` (contains modular search space, intake, evaluation, reporting, and orchestration)
- **Manifest**: `campaign_manifest.json`
- **Local Attempts Artifact**: `direct_arylation_attempts.json` (created/updated during execution)
- **Run Log**: `campaign_run.log` (created/updated during execution)

## Required Environment Variables

Ensure the following environment variables are set before running the script:

```bash
export BO_MCP_API_URL="http://api:8000"
export BO_MCP_API_KEY="[REDACTED]"
export DIRECT_ARYLATION_API_URL="http://direct-arylation-oracle:8000"
```

## Execution Commands

### 1. Start or Resume the Campaign (Default)

To start a new campaign or automatically resume the existing one with the required marker:

```bash
PYTHONPATH=/app python run_direct_arylation.py --max-attempts 60 --poll-s 180
```

### 2. Resume a Specific Campaign by ID

If you want to resume a specific campaign using its ID:

```bash
PYTHONPATH=/app python run_direct_arylation.py --campaign-id <campaign_id> --max-attempts 60 --poll-s 180
```

## Monitoring and Output Tags

The script prints unbuffered, monitor-friendly tagged lines to `stdout` for real-time tracking:

- `[EVENT]`: State changes (e.g., campaign creation, suggestion generation, evaluation start, pausing).
- `[RESULT]`: Full per-experiment analysis and final best candidate reporting.
- `[ALERT]`: Failures, errors, and stop conditions.
- `[HEARTBEAT]`: Liveness indicator showing current progress.

All detailed logs and transport-level details are written to `campaign_run.log` on disk.

## Graceful Shutdown (Stop File)

To pause the campaign gracefully during execution without losing progress:

1. Create a file named `STOP` in the current working directory:
   ```bash
   touch STOP
   ```
2. The script checks for this file at the top of each loop iteration.
3. When detected, the script will:
   - Print `[EVENT] Stop file 'STOP' detected. Initiating graceful shutdown.`
   - Delete the `STOP` file to prevent stale stops on subsequent runs.
   - Pause the campaign on the BO-MCP server.
   - Exit cleanly.
