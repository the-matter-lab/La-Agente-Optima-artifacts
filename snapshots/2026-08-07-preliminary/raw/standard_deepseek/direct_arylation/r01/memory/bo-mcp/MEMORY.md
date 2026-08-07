## BO-MCP Backend Selection for Large Categorical Spaces

When the search space has many categorical parameters whose product exceeds ~100 combinations, the BoTorch backend rejects the campaign with: "Mixed spaces with more than 100 categorical combinations are not yet supported by BoTorch acquisition." Use `"backend": "baybe"` instead — BayBE handles categorical spaces natively without one-hot encoding.

Example: 4 bases × 12 ligands × 4 solvents = 192 categorical combinations → must use BayBE.

## Running BO-MCP Scripts in This Environment

The `/app` directory is read-only, so `uv run python` fails with "Cannot update time stamp of directory 'grafico.egg-info'". Use `PYTHONPATH=/app python3` instead. The system Python at `/opt/venv/bin/python3` has all required dependencies except the `domains` package which is resolved via PYTHONPATH.

## BO-MCP Campaign Script Authoring Checklist

- Use `BoMcpClient.from_env()` — requires `BO_MCP_API_URL` and `BO_MCP_API_KEY`
- Validate intake before creating: `client.validate_intake(intake)`
- Never set `max_iterations` in intake unless the user wants the campaign permanently capped
- Use CLI budget (`--max-attempts`) for per-invocation limits
- Pause (don't terminate) at end of invocation so campaign stays resumable
- Check `next_action()` for loop decisions — never derive from local state
- Emit tagged lines: `[EVENT]`, `[ALERT]`, `[RESULT]`, `[HEARTBEAT]`
- Check stop file at top of each iteration, delete on detection
- Log all attempts to append-only JSONL for full audit trail