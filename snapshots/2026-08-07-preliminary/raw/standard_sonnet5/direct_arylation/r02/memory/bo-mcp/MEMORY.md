## BO-MCP campaign scripting — reusable notes

- `InputParameter` intake shape: `type` in {continuous, discrete, categorical}.
  - categorical: requires `categories` (list[str], >=2 entries), no `bounds`/`values`.
  - discrete: requires `values` (list[float]) and/or `bounds`; a fully
    categorical/discrete crossed search space (all params categorical or
    small discrete lists) is well suited to `backend: "baybe"` — pin it
    explicitly rather than leaving `backend: "auto"` when the user requires
    BayBE, since auto-resolution could silently pick botorch.
  - `Objective`: use `direction: "maximize"|"minimize"` (legacy field) plus
    optional `unit` (display-only, e.g. "%"). `name` must match the key used
    later in `submit_results`' `objective_values` dict.
  - Leave `max_iterations`/`max_observations` unset in intake when a user's
    "N evaluations" is a per-invocation CLI budget, not a permanent campaign
    cap (an intake `max_iterations` cannot be lifted by `reopen`).

- Deriving a CLI attempt-budget (e.g. "exactly 60 attempted evaluations")
  purely from server state, without persisting loop state to disk: call
  `next_action(campaign_id)["n_results"]` for successful attempts, and
  `query_suggestions(campaign_id, status_filter="rejected", limit=500)` for
  failed attempts (assuming the script's only rejection reason is oracle
  failure). `attempted = n_results + len(rejected)`. This is accurate across
  resumes (`--campaign-id`) since both numbers come from the server, not a
  local counter file.

- External-oracle evaluation pattern for BO-MCP loops: when the oracle
  returns a non-2xx/timeout/malformed body, do NOT call `submit_results`
  (BO-MCP's `ResultCreate.objective_values` requires finite floats — no
  sentinel/NaN is accepted). Instead call
  `update_suggestion_status(suggestion_id, "rejected")` so the suggestion is
  retired without submitting a result, and count the attempt locally as
  "failed" for reporting. Do not retry the oracle call internally — one
  oracle POST per suggestion equals exactly one attempt, keeping the budget
  count exact.

- `generate_suggestions` can take minutes and a client-side read timeout
  (`requests.exceptions.Timeout`) does NOT mean nothing was generated
  server-side. On timeout, back off (`--poll-s`, keep 120-300s) and re-query
  `query_suggestions(campaign_id, status_filter="pending")` before treating
  it as a real failure or retrying generation.

- Building a final report that must reflect the *whole* campaign (not just
  the current process's attempts, important after resumes): re-derive it at
  the end of every invocation from `get_results(campaign_id)` (successful,
  has `objective_values`/`parameter_values`) plus
  `query_suggestions(campaign_id, status_filter="rejected")` (failed, no
  objective value) — never from a locally accumulated in-memory/disk list
  across invocations.

- Smoke-testing a campaign script: injecting a deliberate oracle failure
  (e.g. pointing `--oracle-url` at a bad path for one iteration) to verify
  the failure-handling path works is useful, but it leaves a real rejected
  suggestion in that campaign's history. Don't hand back that same
  campaign id for the user's real run if it needs the final report clean —
  document that the real run should start a fresh campaign instead of
  resuming the contaminated smoke-test one.
