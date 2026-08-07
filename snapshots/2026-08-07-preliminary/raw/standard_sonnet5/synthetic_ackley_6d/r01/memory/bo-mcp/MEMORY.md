## BO-MCP campaign scripting notes (from Ackley 6D synthetic benchmark authoring)

- `BoMcpClient` methods (verified via `inspect.signature` in this repo's `uv` env):
  - `create_campaign(intake, *, idempotency_key)` — `idempotency_key` is REQUIRED (not optional).
  - `next_action(campaign_id)` returns a flattened dict: `status`, `iteration`,
    `n_results`, `action`, `reason`, `urgency`. Branch on `action == "bo_generate_suggestions"`.
  - `generate_suggestions(campaign_id, *, batch_size=1, timeout_s=900.0)` — long default timeout; don't shrink it defensively.
  - `submit_results(campaign_id, *, results, idempotency_key, force=False)` — each result dict:
    `{"suggestion_id", "parameter_values", "objective_values"}` (+ optional `measurement_uncertainty`, `metadata`).
  - `update_suggestion_status(suggestion_id, status)` — POSTs to `/api/v1/suggestions/{suggestion_id}/status`
    (NOT campaign-scoped in the URL). Use `status="rejected"` to retire an unexecutable/failed suggestion
    without submitting a result for it (BO-MCP's ResultCreate requires finite floats, so failed evals can't
    be "submitted" — reject the suggestion instead and record the failure locally).
  - `make_idempotency_key(prefix, *parts)` appends a fresh `uuid4` suffix each call — generate it ONCE per
    logical attempt and reuse that same string for retries; calling it again produces a different key.
  - `get_campaign(campaign_id)` returns `name`/`status` — check `status in {"paused","completed"}` to decide
    whether to `lifecycle(action="resume")` vs `lifecycle(action="reopen")` before looping.

- IntakeData essentials for a single-objective continuous BayBE campaign:
  `{"name", "description", "objectives":[{"name","direction":"maximize"|"minimize","unit"}],
  "parameters":[{"name","type":"continuous","bounds":{"lower","upper"}}], "backend":"baybe",
  "batch_size", "initial_design_size", "random_seed", "acquisition_method", "acquisition_beta"}`.
  `acquisition_beta` is only accepted when `acquisition_method="upper_confidence_bound"`.
  Do NOT set `max_iterations`/`max_observations` for a budget that should survive resume/reopen —
  enforce fixed evaluation budgets in the script's own loop instead (fossilizing the intake makes
  a reopened campaign refuse suggestions forever).

- For a campaign-agnostic evaluation budget gate: if the task explicitly defines "attempted" as
  "submitted to BO-MCP OR written to the local artifact", it's correct (and sanctioned by that
  explicit instruction) to derive `attempted_so_far` by reading the local JSONL artifact's row
  count at startup — this is a budget arithmetic gate, not re-deriving the BO progress/continue
  decision (which must still come only from `next_action`). Keep the artifact path deterministic
  from `campaign_id` (e.g. `artifacts/<slug>_<campaign_id>.jsonl`) so resuming with `--campaign-id`
  naturally finds the same file and continues the count correctly; a smoke-tested campaign can only
  be safely handed off for later "real" execution if its artifact file is moved to the same
  `--artifact-dir` the production entrypoint defaults to.

- Smoke-testing a BO-MCP campaign script cheaply: monkeypatch the module-level budget constant
  (e.g. `campaign_mod.TOTAL_BUDGET = 3`) in a throwaway test script rather than editing the shipped
  module, then call the package's `run(...)` function directly. This exercises the real
  create/resume, generate/evaluate/submit, pause, and stop-file code paths against the live BO-MCP
  API without spending the full requested budget, and produces genuine (non-fabricated) results
  that can be handed to the main agent as a head start.
