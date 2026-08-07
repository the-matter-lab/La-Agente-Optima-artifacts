# BO-MCP campaign script authoring — reusable caveats

## BO-MCP intake (verified via REST, BayBE backend)
- Intake dict keys that work: `name`, `description`, `backend` ("baybe"|"botorch"|"auto"),
  `parameters` (`{name, type, bounds:{lower,upper}}` for continuous), `objectives`
  (`{name, direction, unit}`), `batch_size`, `initial_design_size`,
  `acquisition_method`, `random_seed`.
- `acquisition_method` enum (lowercase): auto, expected_improvement,
  noisy_expected_improvement, upper_confidence_bound, probability_of_improvement,
  posterior_mean, posterior_standard_deviation, thompson_sampling, knowledge_gradient,
  active_learning, hypervolume_improvement, simple_regret, *_nonlog variants.
- `update_suggestion_status` accepts only "accepted" | "rejected" | "expired"
  (never "completed"/"failed") — use "rejected" for duplicates and failed evaluations.
- Result rows: `{suggestion_id, parameter_values, objective_values, metadata?}`;
  `metadata` is a closed schema (extra="forbid") — free-form extras must go under
  `metadata.conditions` (primitives only) or be recomputed at report time.
- `client.next_action()` returns flattened `{status, iteration, n_results, action,
  reason, urgency}`; `action == "bo_generate_suggestions"` means continue. A paused
  campaign reports action `review_campaign_status`, so resume it *before* the loop.

## Practical loop patterns that worked
- Budget accounting across resumes: derive already-done count from
  `client.get_results(campaign_id)` / `n_results` — never from disk state.
- For deterministic synthetic objectives, the results table can be rebuilt for
  reporting by recomputing the objective from `get_results` parameter values, so no
  extra provenance fields are needed on the server side.
- Pause at shutdown only when `next_action()["status"] == "running"` — calling pause
  on an already-paused campaign is unnecessary.

## Logfire
- `logfire.debug(line)` with a preformatted string containing `{...}` raises
  FormattingFailedWarning; use `logfire.debug("{detail}", detail=line)` instead.
- `configure_logfire()` + `logfire.instrument_requests()` prints HTTP spans to stdout;
  harmless under a tag-filtering monitor but keep tagged lines distinct.
