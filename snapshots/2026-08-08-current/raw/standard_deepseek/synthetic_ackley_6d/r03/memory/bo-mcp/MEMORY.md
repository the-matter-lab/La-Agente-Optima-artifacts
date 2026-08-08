## BO-MCP Campaign Script Authoring

### BoMcpClient.from_env() pattern
- Requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars; fails fast if missing.
- `client.make_idempotency_key(prefix, *parts)` generates UUID-suffixed keys.
- `client.validate_intake(intake)` dry-runs before `create_campaign`.
- `client.next_action(campaign_id)` returns `{status, iteration, n_results, action, reason, urgency}`. Branch on `action == "bo_generate_suggestions"` to continue.
- `client.generate_suggestions(campaign_id, batch_size=1)` returns `{success, suggestions: [{suggestion_id, parameter_values, ...}]}`.
- `client.submit_results(campaign_id, results=[{suggestion_id, parameter_values, objective_values}], idempotency_key=...)` — each submission needs a fresh idempotency key.
- `client.lifecycle(campaign_id, action="pause"|"resume"|"terminate"|"reopen")`.
- `client.get_campaign(campaign_id)` returns campaign metadata including `status`.
- `client.update_suggestion_status(suggestion_id, "rejected")` retires unexecutable suggestions.

### Error contract
- Non-2xx → `BoMcpClientError`
- 2xx with `success: false` → `BoMcpOperationError` (`.payload` has `errors`, `field_errors`)

### Campaign intake shape (BayBE backend)
- `name`, `description`, `backend`, `batch_size`
- `parameters`: list of `{name, type: "continuous"|"discrete"|"categorical", bounds: {lower, upper}}`
- `objectives`: list of `{name, target_mode: "maximize"|"minimize"|"match", unit}`
- Do NOT set `max_iterations` unless the campaign should be permanently capped.

### Loop policy
- Server owns progress; never persist loop state to disk.
- `next_action` drives continue/stop; artifact files are append-only.
- Pause at end of invocation (not terminate) so campaign can resume.
- `--campaign-id` enables resume/reopen on re-run.

### Tagged stdout for monitor
- `[EVENT]` state changes, `[ALERT]` failures, `[RESULT]` per-eval, `[HEARTBEAT]` liveness.
- Print unbuffered with `flush=True`.

### Synthetic evaluator pattern
- Deterministic, no external calls, returns `{parameter_values, objective_values, raw_response, status, failure_reason}`.
- Failed evaluations: reject the suggestion via `update_suggestion_status` and continue.