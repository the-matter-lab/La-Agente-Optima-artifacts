## BO-MCP Script Authoring Notes

### Execution Environment
- `uv run python` fails with "Cannot update time stamp of directory 'grafico.egg-info'" because /app is read-only. Use `python3` directly with `sys.path.insert(0, '/app')` instead.
- The venv at `/opt/venv/bin/python3` has `requests` and other deps pre-installed.

### BO-MCP Client Usage
- `BoMcpClient.from_env()` requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars.
- `next_action(campaign_id)` returns `action` field: `bo_generate_suggestions` (generate new), `bo_submit_results` (pending suggestions exist), or others (stop).
- Must handle `bo_submit_results` action: query pending suggestions with `client.query_suggestions(cid, status_filter="pending")` and evaluate them.
- Campaign lifecycle: create → loop (next_action → generate/query → evaluate → submit) → pause at end.
- Resume: `client.lifecycle(cid, action="resume")` for paused, `action="reopen"` for completed.
- `max_iterations` should NOT be set in intake (immutable); use client-side budget instead.
- Idempotency keys: use `BoMcpClient.make_idempotency_key()` for create/submit operations.

### Key API Shapes
- Campaign intake: `name`, `parameters` (list of `{name, type, bounds}`), `objectives` (list of `{name, direction, unit}`), `backend`, `random_seed`, `initial_design_size`, `batch_size`, `acquisition_method`.
- Result submission: `{suggestion_id, parameter_values, objective_values}` in `results` list.
- Suggestion response: `{suggestion_id, parameter_values, provenance, status}`.
