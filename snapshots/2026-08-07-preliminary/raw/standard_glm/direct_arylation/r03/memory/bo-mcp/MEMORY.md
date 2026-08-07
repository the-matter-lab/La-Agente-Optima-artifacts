## BO-MCP Campaign Script Authoring Notes

- `BoMcpClient.from_env()` requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars.
- Campaign intake: `name`, `parameters` (list of InputParameter dicts), `objectives` (list of Objective dicts), `batch_size`.
- Parameter types: `categorical` (needs `categories`), `discrete` (needs `values`), `continuous` (needs `bounds`).
- Objective: `name`, `direction` ("maximize"/"minimize"), `unit` (display only).
- `create_campaign(intake, idempotency_key=...)` returns dict with `campaign_id` on success.
- `next_action(campaign_id)` returns dict with `action` ("bo_generate_suggestions" means continue).
- `generate_suggestions(campaign_id, batch_size=1, timeout_s=300)` — can take minutes for wide discrete spaces.
- `submit_results(campaign_id, results=[...], idempotency_key=..., force=False)` — use `force=True` for replicates.
- `lifecycle(campaign_id, action="pause"/"resume"/"terminate"/"reopen")`.
- Idempotency keys: `BoMcpClient.make_idempotency_key(prefix, *parts)` — generates UUID-suffixed key.
- Loop policy: server owns progress; don't persist loop state to disk; CLI budgets are per-invocation.
- `PYTHONPATH=/app` needed for imports from the grafico package when running scripts outside /app.
- Logfire: `from grafico.core.logfire_config import configure_logfire; configure_logfire(); logfire.instrument_requests()`.
- The `uv run` build can fail with egg-info timestamp errors on read-only filesystems; use `PYTHONPATH=/app` instead.
