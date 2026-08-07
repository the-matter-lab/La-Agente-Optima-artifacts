# BO-MCP Campaign Script Authoring Guidelines

## Duplicate Prevention
To prevent evaluating duplicate coordinates in BO-MCP campaigns:
1. Maintain a set of evaluated coordinates in memory.
2. At startup, populate this set from both the local results log and the server-persisted results (via `client.get_results(campaign_id)`).
3. Before evaluating any new suggestion, check if its coordinates are already in the set.
4. If they are, reject the suggestion on the server using `client.update_suggestion_status(suggestion_id, "rejected")` and continue the loop to request a new suggestion.

## Budget Enforcement
To enforce a campaign-wide budget of attempted evaluations across resumes:
1. Read the local append-only results log at startup to count the number of attempted evaluations.
2. If the count is already at or above the budget, exit immediately.
3. Otherwise, continue the loop and increment the attempt counter for each evaluation (including failed ones).
4. Stop the loop when the attempt counter reaches the budget.

## Graceful Shutdown (Stop File)
1. Check for the presence of a `STOP` file at the top of each loop iteration.
2. If detected, print `[EVENT]`, delete the `STOP` file, pause the campaign on the server using `client.lifecycle(campaign_id, action="pause")`, and exit gracefully.
