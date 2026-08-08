# BO-MCP Campaign Script Authoring Learnings

## 1. Counting Attempts and Handling Failures
- When running a campaign with a fixed budget of attempted evaluations (both successful and failed), the server's `n_results` only counts successful evaluations (since failed evaluations cannot be submitted as results with finite objective values).
- To count total attempts (successful + failed) across resumes without persisting local state to disk, query all suggestions using `client.query_suggestions(campaign_id)`.
- Count the number of suggestions with status `"completed"` or `"rejected"`.
- If an evaluation fails, update the suggestion status to `"rejected"` using `client.update_suggestion_status(suggestion_id, "rejected")`. This marks the attempt as completed on the server and allows the server to recommend the same coordinates again if needed (replicate policy).

## 2. Reusing Pending Suggestions
- Before generating new suggestions, always check if there are any `"pending"` suggestions by querying suggestions with `status_filter="pending"`.
- If pending suggestions exist, reuse them instead of calling `generate_suggestions`, which avoids duplicate generation and saves time/compute.

## 3. Logfire Request Instrumentation
- Always add Logfire request instrumentation near the script header for BO/PySCF runs:
  ```python
  import logfire
  from grafico.core.logfire_config import configure_logfire
  configure_logfire()
  logfire.instrument_requests()
  ```


## 4. Campaign Status Handling and Automatic Resumption
- When resuming an existing campaign, the server's `next_action` may return `review_campaign_status` with status `"paused"` or `"completed"`.
- To handle this dynamically and automatically, check the campaign status returned by `next_action`.
- If the status is `"paused"`, call `client.lifecycle(campaign_id, action="resume")` and `continue` the loop to re-evaluate the next action.
- If the status is `"completed"`, call `client.lifecycle(campaign_id, action="reopen")` and `continue` the loop to re-evaluate the next action.
- This ensures the campaign is automatically transitioned to `"running"` before attempting to generate suggestions or submit results.
