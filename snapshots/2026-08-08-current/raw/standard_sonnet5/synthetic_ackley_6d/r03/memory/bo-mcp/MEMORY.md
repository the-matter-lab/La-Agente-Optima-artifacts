## BO-MCP API implementation gotchas (learned while authoring Ackley-6D BayBE campaign)

- `ResultCreate` (submitted via `submit_results`) accepts an optional
  `metadata` object (with a `conditions: dict[str, primitive]` field usable
  for small scalar side-values), but the persisted `ResultResponse` returned
  by `GET /api/v1/results/{campaign_id}` / `client.get_results()` does NOT
  include `metadata` at all — only `parameter_values`, `objective_values`,
  `suggestion_id`, `source`, `submitted_by`, timestamps. Don't rely on
  metadata round-tripping for reporting; if you need an auxiliary/raw value
  later, either recompute it from `parameter_values` (cheap/safe when the
  objective is a pure deterministic function) or store it in your own local
  artifact file instead.
- BO-MCP's result schema requires finite `objective_values` (NaN/inf are
  rejected with 422) — there is no way to submit a "failed evaluation" as a
  result. To track failed candidate evaluations for reporting/budget
  purposes: catch the failure locally, call
  `client.update_suggestion_status(suggestion_id, "rejected")` to release
  the suggestion (valid enum values: `accepted`/`rejected`/`expired`), and
  append the failure to your own local append-only log (this is legitimate
  even under the "don't persist loop state" policy, since it's not
  BO-progress bookkeeping the server already owns — BO-MCP has no concept
  of a failed external evaluation at all).
- `client.next_action(campaign_id)["action"]` should be checked for the
  exact string `"bo_generate_suggestions"` to mean "continue"; any other
  value (including ones not enumerated in the client docstring) should be
  treated as a stop signal.
- `client.get_campaign(campaign_id)` returns top-level `name` and `status`
  fields directly (flat `CampaignResponse`, no nesting) — convenient for
  ownership-marker checks and lifecycle branching (`paused` → `resume`,
  `completed` → `reopen`).
- For continuous-only search spaces, exact duplicate suggestions are
  astronomically unlikely from the BO backend, but if a task requires
  "never evaluate the same point twice", it's cheap and robust to keep a
  `seen` set of rounded parameter tuples (from server results + any local
  failure log) each loop iteration and reject/skip any suggestion matching
  it via `update_suggestion_status(..., "rejected")` without spending
  evaluation budget.
