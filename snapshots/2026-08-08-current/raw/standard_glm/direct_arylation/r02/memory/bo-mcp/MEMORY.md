## BO-MCP Campaign Script Authoring Notes

### Oracle Response Handling
When parsing oracle JSON responses, use explicit key membership checks (`if "yield" in body`) rather than truthiness checks (`body.get("yield") or ...`). A yield of `0.0` is falsy in Python but is a valid measurement. The `or` chain silently skips it.

### BO-MCP next_action Responses
The `next_action` endpoint can return `bo_submit_results` when there are pending (unevaluated) suggestions. The campaign loop must handle this by querying pending suggestions and evaluating them, not just stopping. Only stop when the action is something other than `bo_generate_suggestions` or `bo_submit_results`.

### uv run Build Failures
In read-only `/app` environments, `uv run python` may fail with "Cannot update time stamp of directory 'grafico.egg-info'". Use the venv Python directly with `PYTHONPATH=/app:. /opt/venv/bin/python3` instead.

### Campaign Intake: max_iterations
Never set `max_iterations` in the campaign intake unless the user explicitly wants a permanent cap. The intake is immutable; a fossilized cap blocks reopens. Use CLI `--max-attempts` for per-invocation budgets.
