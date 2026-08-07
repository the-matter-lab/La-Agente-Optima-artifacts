## BO-MCP Campaign Script Authoring (2025-08-07)

### Client usage pattern
- `BoMcpClient.from_env()` reads `BO_MCP_API_URL` and `BO_MCP_API_KEY` — both required.
- `validate_intake(intake)` dry-runs before `create_campaign`.
- `create_campaign(intake, idempotency_key=...)` returns `{success, campaign_id, ...}`.
- `next_action(campaign_id)` returns `{action, status, iteration, n_results}` — branch on `action == "bo_generate_suggestions"`.
- `generate_suggestions(campaign_id, batch_size=N)` returns `{success, suggestions: [{suggestion_id, parameter_values, ...}]}`.
- `submit_results(campaign_id, results=[{suggestion_id, parameter_values, objective_values}], idempotency_key=...)` — `force=True` for replicates.
- `update_suggestion_status(suggestion_id, "rejected")` for failed evaluations.
- `lifecycle(campaign_id, action="pause"|"resume"|"reopen"|"terminate")`.
- `get_diagnostics(campaign_id, verbosity="standard", timeout_s=...)` — expensive, call once at end.
- `get_results(campaign_id)` returns list of result rows.
- `make_idempotency_key(prefix, *parts)` generates stable keys.

### Intake payload shape (BayBE backend)
- `name`, `description`, `backend: "baybe"`, `parameters: [{name, type, bounds}]`, `objectives: [{name, target_mode, unit}]`, `batch_size`, `initial_design_size`, `random_seed`.
- Leave `max_iterations`/`max_observations` unset for CLI-budgeted campaigns.

### Result submission shape
- `results: [{suggestion_id, parameter_values, objective_values}]`
- `objective_values` is `{objective_name: float}`.

### Loop policy
- Server owns progress — use `next_action` for continue/stop, never local counters.
- Pause at end of invocation, never terminate.
- Resume with `--campaign-id`; script auto-detects status and resumes/reopens.
- Stop file: check at top of each iteration, delete on trigger, exit through normal shutdown.