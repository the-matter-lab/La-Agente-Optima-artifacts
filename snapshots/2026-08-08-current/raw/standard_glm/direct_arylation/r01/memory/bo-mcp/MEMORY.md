## BO-MCP Campaign Script Authoring Notes

### Backend Selection
- BoTorch rejects mixed spaces with >100 categorical combinations at intake validation.
- BayBE handles large categorical spaces natively and validates fine.
- Always validate intake before creating a campaign to catch backend incompatibilities early.

### Acquisition Method Enum
- The API uses lowercase snake_case enum values: `noisy_expected_improvement`, `expected_improvement`, etc.
- The OpenAPI `AcquisitionMethod` class docs list semantic families but not the exact enum strings; check the 422 error for valid values.

### PYTHONPATH
- The `/app` directory is read-only and not on `sys.path` by default in the venv.
- Add `sys.path.insert(0, "/app")` in the entrypoint script so `domains.*` and `grafico.*` are importable without explicit `PYTHONPATH=/app`.

### BoMcpClient Usage
- `from_env()` requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars.
- `validate_intake(intake)` sends `{"intake": intake}` to `POST /api/v1/campaigns/validate`.
- `create_campaign(intake, idempotency_key=...)` sends `{"intake": intake}` to `POST /api/v1/campaigns`.
- `next_action(campaign_id)` uses `POST /api/v1/campaigns/status/batch` with `{"campaign_ids": [id], "verbosity": "minimal"}`.
- `generate_suggestions(campaign_id, batch_size=1)` can take minutes for large spaces; default timeout is 900s.
- `submit_results(campaign_id, results=[...], idempotency_key=...)` — use `force=True` for replicates.
- Campaign lifecycle: `pause` at end of invocation, `resume` to continue, `reopen` for completed campaigns.
- Do NOT set `max_iterations` in intake unless the user explicitly wants a permanent cap.

### Artifact Design
- JSONL for per-attempt records (append-only).
- `final_report.json` for summary with best yield, best conditions, counts, all attempts.
- Loop state must NOT be read from artifacts; `next_action` is the sole authority.
