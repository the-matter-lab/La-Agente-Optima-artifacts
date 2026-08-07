## BO-MCP campaign scripting caveats (observed & verified)

- A freshly created campaign reports `status="created"`, not `"running"`. A "make sure it
  is running" helper must treat `created` as OK (only `paused`→resume, `completed`→reopen,
  anything else → alert), otherwise every fresh run prints a spurious failure line.
- `client.next_action(campaign_id)` returns `status`, `iteration`, `n_results`, `action`,
  `reason`, `urgency`. `n_results` is the server-side authority for a campaign-wide
  evaluation budget: `budget_this_invocation = max(0, total_budget - n_results)`. This keeps
  budgets exact across resumes without persisting any local loop state.
- Suggestion status enum is only `accepted | rejected | expired` (no `failed`, and
  `completed` is set implicitly by submitting a result with the `suggestion_id`). Record
  evaluation failures in the local artifact and mark the suggestion `rejected`.
- `generate_suggestions` response: `{"success", "suggestions": [{"suggestion_id",
  "parameter_values", "provenance", ...}], "iteration"}`; server result rows from
  `get_results` carry `parameter_values`, `objective_values`, `suggestion_id`, `created_at`.
  `suggestion_id` copies straight into a result row.
- `client.submit_results` / `generate_suggestions` raise `BoMcpOperationError` on a 2xx
  `success:false` envelope, so wrap them in try/except and print an `[ALERT]` instead of
  checking a return flag.
- BayBE backend (pinned `backend="baybe"`) accepts `acquisition_method=
  "upper_confidence_bound"` with `acquisition_beta`, `initial_design_size`, `batch_size`,
  and `random_seed`; validate with `validate_intake` before creating.
- For a per-invocation campaign report that must cover the *whole* campaign, rebuild the
  table from `get_results()` (successes) plus failure rows re-read from prior artifact
  JSONL files. Reading artifacts for reporting is fine; only loop decisions must not.
- Deterministic/noiseless synthetic evaluators: dedupe suggested points against a set of
  rounded coordinate tuples built from `get_results()` and reject duplicates before
  evaluating, so they consume no budget (the replicate/force path is for noisy objectives).

## BO-MCP loop robustness (learned from a killed-run post-mortem)

- **`BoMcpClient` does NOT wrap `requests` exceptions.** `_request` calls
  `session.request(...)` directly, so `requests.exceptions.ReadTimeout` /
  `ConnectionError` propagate raw and are *not* subclasses of `BoMcpClientError`.
  Always catch `(BoMcpClientError, BoMcpOperationError, requests.exceptions.RequestException)`
  around generate/submit/diagnostics, otherwise a slow server call kills the campaign script.
- **Never break the loop on `action != "bo_generate_suggestions"`.** After a run dies
  between generation and submission, the server holds pending suggestions and
  `next_action` returns `bo_submit_results`. Treat both actions as work, and always
  `query_suggestions(status_filter="pending")` *before* generating so orphaned suggestions
  are consumed instead of stranding evaluation-budget slots.
- **BayBE suggestion generation is slow and silent, and grows with campaign size**
  (~90 s at ~22 results in 6 continuous dims, minutes later on). Wrap every blocking
  BO-MCP call in a worker thread and print a `[HEARTBEAT]` tick every ~60 s; a monitored
  run with no output for minutes gets killed by the operator/harness. Print an `[EVENT]`
  naming the iteration and batch size *before* the call. Fewer, larger batches cut total
  wall time because each generation is one server-side model fit.
- **`get_diagnostics` cold-compute is the worst offender** (~148 s at 22 results, ~259 s at
  26, ~340 s at 60; results are cached afterwards, so a repeat call looks instant and
  misleads timing tests). Make it opt-in via a `--diagnostics-verbosity none|minimal|
  standard|detailed` flag defaulting to `none` when the report does not need it.
- Trap `SIGINT`/`SIGTERM` (set a flag checked at the top of the iteration) and route
  exceptions through the same finalize path, so a killed/aborted run still writes artifacts
  and pauses the campaign. Signals are only delivered to the main thread between
  `future.result(timeout=...)` ticks, which is another reason to poll blocking calls.
- Make a zero-remaining-budget invocation an explicit, instant **report-only mode**
  (`budget = max(0, total - n_results)` → skip loop, rebuild table from `get_results`).
  It gives the operator a safe, idempotent verification command that cannot overrun budget.
