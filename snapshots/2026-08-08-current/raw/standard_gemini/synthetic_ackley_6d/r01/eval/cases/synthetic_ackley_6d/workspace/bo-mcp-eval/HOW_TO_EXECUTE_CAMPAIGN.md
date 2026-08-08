# How to Execute the 6D Ackley Synthetic Optimization Campaign

This document explains how to run, resume, and validate the synthetic benchmark optimization campaign over the 6D Ackley surface.

## Campaign Details
- **Campaign Ownership Marker**: `akg-eval-6840ad6b86bb414189216d3f126bba73`
- **Repeat Cache-Buster Nonce**: `23cffb46-6ea4-4773-af09-39705022e946`
- **Objective**: `surface_response` (maximize, normalized unitless response)
- **Search Space**: 6 continuous parameters `x_1`..`x_6` bounded in `[0.0, 1.0]`
- **Evaluation Budget**: Exactly 60 attempted evaluations

---

## Environment Setup

Ensure the following environment variables are set before running the script:

```bash
export BO_MCP_API_URL="http://api:8000"
export BO_MCP_API_KEY="[REDACTED]"
```

---

## Execution Commands

### 1. Start a New Campaign
To start a brand-new campaign and run it to completion (60 evaluations):

```bash
python run_synthetic_ackley_6d.py --budget 60
```

### 2. Resume an Existing Campaign
If the campaign is interrupted or paused, you can resume it by passing the `--campaign-id` argument:

```bash
python run_synthetic_ackley_6d.py --campaign-id <campaign_id> --budget 60
```

---

## Output and Logging

- **Run Log**: Detailed logs are written to `campaign.log` in the current working directory.
- **Results Artifact**: The evaluation history is saved to `artifacts/results_artifact.json`.
- **Stdout Tags**:
  - `[EVENT]`: State changes (e.g., campaign creation, pause, resume, stop file detection).
  - `[ALERT]`: Failures and stop conditions.
  - `[RESULT]`: Full per-experiment analysis.
  - `[HEARTBEAT]`: Liveness indicator.

---

## Graceful Shutdown (Stop File)

To pause the campaign execution gracefully at the top of the next iteration:
1. Create a file named `STOP` in the current working directory:
   ```bash
   touch STOP
   ```
2. The script will detect the file, print `[EVENT] Stop file 'STOP' detected. Initiating graceful shutdown.`, delete the `STOP` file, pause the campaign on the BO-MCP server, and exit.
3. You can resume the campaign later using the resume command.

---

## Duplicate Prevention

To strictly enforce the user contract ("Do not evaluate the same point more than once"), the script implements a robust duplicate detection and rejection mechanism:
1. **Multi-Source History**: At each iteration, the script loads all previously evaluated coordinates from both the local results artifact (`artifacts/results_artifact.json`) and the BO-MCP server (via `client.get_results`).
2. **Precision-Aware Comparison**: It compares the newly suggested coordinates against the history using a high-precision float comparison (`math.isclose` with a tolerance of `1e-7`).
3. **Graceful Rejection**: If a duplicate is detected, the script prints `[ALERT] Suggested candidate is a duplicate of an already evaluated point. Rejecting suggestion <suggestion_id>.`, rejects the suggestion on the BO-MCP server (marking it as `rejected`), and continues the loop to generate a fresh, unique suggestion. This ensures that duplicate points are never evaluated or counted toward the budget.


---

## Capturing the Campaign ID

When a new campaign is created, the script prints the campaign ID to stdout in the following format:

```
BO_MCP_CAMPAIGN_ID=<campaign_id>
```

You can capture this ID from the stdout stream or find it in `campaign.log`.
