# BO-MCP campaign script authoring — reusable caveats

## BO-MCP payload shapes (observed, REST API)
- Suggestion records from `generate_suggestions()["suggestions"]` / `query_suggestions()` use keys
  `suggestion_id` (NOT `id`), `status`, `parameter_values`, `iteration`, `generation_method`.
  Submitting a result with `suggestion_id=None` leaves the suggestion `pending` forever, and
  `next_action` then returns `bo_submit_results` on every later iteration, which silently stalls a
  loop that only continues on `bo_generate_suggestions`.
- Therefore always handle `action == "bo_submit_results"` by picking up
  `query_suggestions(cid, status_filter="pending")[0]` and evaluating it — this also recovers a run
  killed between generate and submit.
- Result rows from `get_results()` use `parameter_values` / `objective_values` (+ `id`,
  `suggestion_id`, `created_at`).
- Discrete numeric parameters declared with float `values` (e.g. 90.0) accept int values (90) in
  submitted `parameter_values`; suggestions come back as floats, so snap/canonicalize before
  calling an oracle that keys on exact grid values.
- Recording failed evaluations without penalizing them: `update_suggestion_status(sid, "rejected")`.
  A server-derived attempt budget is then `len(get_results()) + len(query_suggestions(status_filter="rejected"))`,
  which survives restarts with no local state.
- Duplicate/replicate submissions: catch `BoMcpOperationError` from `submit_results` and retry once
  with `force=True` **and a fresh idempotency key** (the rejection is cached under the old key).

## Logfire in campaign entrypoints
- `configure_logfire()` writes its console exporter to **stdout**, which pollutes the tagged-line
  stream a monitor reads. Use `configure_logfire(console=False)` and keep `logfire.instrument_requests()`.
- `logfire.info/debug` need a template plus kwargs (`logfire.debug("{m}", m=msg)`); passing a
  preformatted string containing braces raises `FormattingFailedWarning`.

## Running workspace scripts that import /app packages
- From the workspace dir: `uv run --project /app python -u run_<slug>.py`. Keeps cwd (so artifacts,
  STOP file and logs stay in the workspace) while resolving the /app uv environment.
