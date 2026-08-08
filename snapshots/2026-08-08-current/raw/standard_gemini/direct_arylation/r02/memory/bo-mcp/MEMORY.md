# BO-MCP Campaign Script Authoring Guidelines

## 1. Campaign Progress and State Ownership
- **Server as Single Source of Truth**: The BO-MCP server owns campaign progress. Do not persist loop state to disk (e.g., no `campaign_state.json` or local iteration counters).
- **Reconstructing Attempted Counts**: To track the number of attempted evaluations (including failures) across resumes, query all suggestions from the server using `client.query_suggestions(campaign_id)`.
  - Completed suggestions (`status == "completed"`) represent successful evaluations.
  - Rejected suggestions (`status == "rejected"`) represent failed evaluations.
  - Total attempts = `completed_count + rejected_count`.
  - This allows perfect reconstruction of the attempt count without local state.

## 2. Suggestion Handling
- **Query Pending First**: Always query for pending suggestions (`status_filter="pending"`) before generating new ones. This avoids duplicate generation and respects the server's state.
- **Graceful Rejection**: If an evaluation fails, update the suggestion status to `"rejected"` using `client.update_suggestion_status(suggestion_id, "rejected")`. This retires the suggestion instance without excluding the coordinates from future generation.

## 3. Execution and Resuming
- **Lifecycle Management**: Use `client.lifecycle(campaign_id, action="resume")` to resume a paused campaign, and `client.lifecycle(campaign_id, action="reopen")` to reopen a completed campaign.
- **Pause at End of Invocation**: Always pause the campaign on the server at the end of an invocation using `client.lifecycle(campaign_id, action="pause")`.

## 4. Stop-File Behavior
- Check for the existence of a stop file (e.g., `STOP`) at the top of each loop iteration before generating suggestions.
- If detected, delete the stop file, pause the campaign on the server, and exit gracefully.
