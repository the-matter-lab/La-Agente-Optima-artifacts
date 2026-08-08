# BO-MCP Campaign Script Authoring Guidelines

## 1. Campaign Lifecycle and Loop Policy
- **Single Source of Truth**: The BO-MCP server owns campaign progress. Derive each iteration's continue/stop decision from `BoMcpClient.next_action(campaign_id)` and never persist loop state to disk (no `campaign_state.json` or iteration counters).
- **Resumption**: Support an optional `--campaign-id` argument so a killed or paused run resumes by re-running the same command. If not provided, query existing campaigns on the server using `client._json_request("GET", "/api/v1/campaigns")` to find a campaign with the required marker/name and resume it.
- **Lifecycle Actions**:
  - Pause at the end of an invocation: `client.lifecycle(campaign_id, action="pause")`.
  - Resume a paused campaign: `client.lifecycle(campaign_id, action="resume")`.
  - Reopen a completed campaign: `client.lifecycle(campaign_id, action="reopen")`.
  - Never rebuild an existing campaign by replaying its results as seeds.

## 2. Suggestion and Attempt Tracking
- **Attempt Counting**: Count total attempts (successful + failed) across resumes by querying suggestions from the server:
  ```python
  suggestions = client.query_suggestions(campaign_id)
  attempts_count = sum(1 for s in suggestions if s["status"] in ("completed", "rejected"))
  ```
- **Reusing Suggestions**: If there are pending suggestions, reuse them instead of generating new ones:
  ```python
  pending = [s for s in suggestions if s["status"] == "pending"]
  if pending:
      suggestion = pending[0]
  else:
      gen_resp = client.generate_suggestions(campaign_id, batch_size=1)
      suggestion = gen_resp["suggestions"][0]
  ```
- **Failure Handling**: If an evaluation fails, update the suggestion status to `"rejected"` using `client.update_suggestion_status(suggestion_id, "rejected")`. This marks the attempt as completed on the server and allows the server to recommend the same coordinates again if needed (replicate policy).

## 3. Execution and Environment
- **Python Execution**: When running in environments where editable package builds fail (e.g., due to read-only file systems or permission issues), run python directly with `PYTHONPATH=/app python` instead of `uv run python`.
- **Logfire Instrumentation**: Add Logfire request instrumentation near the script header:
  ```python
  import logfire
  from grafico.core.logfire_config import configure_logfire
  configure_logfire()
  logfire.instrument_requests()
  ```
- **Unbuffered Output**: Ensure stdout is unbuffered so monitor-friendly tags (`[EVENT]`, `[RESULT]`, `[ALERT]`, `[HEARTBEAT]`) are printed immediately:
  ```python
  import sys
  sys.stdout.reconfigure(line_buffering=True)
  ```
