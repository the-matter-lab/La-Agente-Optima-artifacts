# How to Execute the Direct Arylation Optimization Campaign

This campaign optimizes the reaction yield of a direct arylation reaction using the BO-MCP architecture.

## Required Environment Variables

Before running the campaign, ensure the following environment variables are set:

- `BO_MCP_API_URL`: The base URL of the BO-MCP REST API (e.g., `http://api:8000`).
- `BO_MCP_API_KEY`: The API key for authenticating with the BO-MCP REST API.
- `DIRECT_ARYLATION_API_URL`: The base URL of the direct arylation reaction-yield oracle service.

## Execution Commands

### 1. Start a New Campaign
To start a new campaign with a budget of 60 attempted evaluations:
```bash
PYTHONPATH=. python run_direct_arylation.py --budget 60
```

### 2. Resume an Existing Campaign
To resume a paused or interrupted campaign, pass the campaign ID:
```bash
PYTHONPATH=. python run_direct_arylation.py --campaign-id <campaign_id> --budget 60
```

## Stop-File Behavior

The campaign supports graceful interruption via a stop file.
- By default, the script checks for a file named `STOP` in the current working directory at the start of each iteration.
- If the `STOP` file is detected, the script will:
  1. Print `[EVENT] Stop file 'STOP' detected. Pausing campaign and exiting.`
  2. Delete the `STOP` file so that subsequent resume commands are not immediately stopped.
  3. Pause the campaign on the BO-MCP server.
  4. Exit gracefully.

To trigger a graceful stop:
```bash
touch STOP
```

## Output and Logging Tags

The script prints unbuffered tagged lines to `stdout` for monitoring:

- `[EVENT]`: State changes (e.g., campaign creation, resuming, pausing, reopening).
- `[ALERT]`: Failures, errors, and stop conditions.
- `[RESULT]`: Full per-experiment analysis and final summary results.
- `[HEARTBEAT]`: Liveness checks printed periodically.

At the very end of a successful run, the script prints:
```
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

## Expected Artifacts

- `campaign_manifest.json`: Lists the package modules, entrypoint, and artifact directory.
- Logfire logs: Detailed request instrumentation and execution logs are sent to Logfire.
