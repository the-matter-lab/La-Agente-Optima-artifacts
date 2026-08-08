## BO-MCP Campaign Script Authoring Notes

- `BoMcpClient.from_env()` requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars.
- `validate_intake()` returns `{"valid": True/False, "errors": [...], "warnings": [...]}` — check `valid`, not `success`.
- `create_campaign()` returns `{"success": True/False, "campaign_id": "..."}` — check `success`.
- `generate_suggestions()` returns `{"success": True/False, "suggestions": [...]}` — check `success`.
- `submit_results()` returns `{"success": True/False, "result_ids": [...]}` — check `success`.
- `next_action()` returns `{"action": "bo_generate_suggestions" | ..., "n_results": N, ...}`.
- `get_results()` returns a list of result dicts with `parameter_values` and `objective_values`.
- Campaign lifecycle: `lifecycle(action="pause"|"resume"|"terminate"|"reopen")`.
- Idempotency keys: use `BoMcpClient.make_idempotency_key(prefix, *parts)` for create and submit.
- The `initial_design_size` field controls Sobol/random warmup before model-driven acquisition.
- BayBE backend: `backend="baybe"`, supports `expected_improvement` acquisition.
- Result metadata can include `conditions` dict with primitive values for extra data like `raw_response`.
- On resume, query `get_results()` to count prior evaluations and adjust the remaining budget.
