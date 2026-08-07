## BO-MCP campaign script authoring — reusable caveats

- `ValidateIntakeResponse` (POST /api/v1/campaigns/validate) has no `success`
  field — it uses `valid: bool` + `errors`/`warnings`. `client._json_request`
  only auto-raises `BoMcpOperationError` when a 2xx body has `success is
  False`, so it will NOT raise on a rejected validate-intake call. Scripts
  must explicitly check `validation.get("valid")` themselves.
- `BoMcpClient.generate_suggestions` / other calls do not wrap
  `requests.exceptions.RequestException` (e.g. read timeouts) — they
  propagate directly from `requests`. Catch
  `requests.exceptions.RequestException` around `generate_suggestions` and
  recover via `query_suggestions(campaign_id, status_filter="pending")`
  rather than retrying blindly (per the client docstring: a read timeout
  does not prove nothing was produced).
- `client.get_campaign(campaign_id)` exists (returns `status`, `iteration`,
  etc.) even though it isn't mentioned in the client docstring's lifecycle
  list — use it to check campaign status before an unconditional
  pause/resume/reopen lifecycle call (e.g. don't call `action="resume"` on a
  campaign that is already `running`; branch on `status in {"paused",
  "completed"}`).
- BO-MCP result submission (`submit_results`) only accepts finite
  `objective_values` (NaN/inf rejected with 422) — there is no way to
  persist a "failed" result server-side. Any oracle/eval failure that must
  count toward an attempt budget has to be tracked in a local
  provenance artifact (e.g. JSONL) instead, and the failed suggestion should
  be retired via `update_suggestion_status(suggestion_id, "rejected")` so it
  doesn't stay pending forever.
- For a "CLI-invocation attempt budget" that must survive resume without
  ever exceeding a fixed total (e.g. "exactly 60 oracle calls"), reconcile at
  startup: `successful_attempts = len(client.get_results(campaign_id))`
  (server truth) + `failed_attempts` counted from the local JSONL artifact
  filtered by `campaign_id` (the only place failures are recorded). This one
  read of the artifact at startup is reconciliation, not a per-iteration
  loop-decision readback, so it doesn't violate the "artifacts are
  provenance only" rule.
- `grafico.core.logfire_config.configure_logfire()` defaults to also
  printing spans/logs to the console (stdout) via Logfire's console
  exporter, which pollutes a tagged-stdout-only contract
  (`[EVENT]`/`[ALERT]`/`[RESULT]`/`[HEARTBEAT]`). Call
  `configure_logfire(console=False)` in BO/PySCF campaign scripts that must
  keep stdout limited to tagged lines for a monitoring wrapper.
- `BoMcpClient.make_idempotency_key(prefix, *parts)` already appends a fresh
  uuid4 hex suffix, so it's safe to call fresh for every create/submit
  attempt without manual uuid handling.
