## BO-MCP Campaign Script Authoring Notes

- **Container `/app` is read-only**: `uv run python` fails because it tries to rebuild the editable grafico package. Use `PYTHONPATH=/app python3` instead. Scripts should also add `/app` to `sys.path` as a fallback.
- **`from __future__ import annotations`** must be the very first statement after the module docstring — no `sys.path` manipulation or other imports before it.
- **BoMcpClient.from_env()** requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` env vars.
- **Campaign lifecycle**: create → loop (next_action → generate_suggestions → evaluate → submit_results) → pause (not terminate). Resume with `action="resume"`, reopen completed with `action="reopen"`.
- **Duplicate results**: If submission fails with duplicate/E004, retry with `force=True` and a **new** idempotency key.
- **Loop state**: Server owns progress via `next_action()`. Never persist loop state to disk. Artifact files are append-only provenance.
- **Logfire**: `from grafico.core.logfire_config import configure_logfire; configure_logfire(); logfire.instrument_requests()` — add near script header.
