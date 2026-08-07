## BO-MCP campaign scripting — reusable lessons

- For a CLI `--budget`/`--max-attempts` that must hold across kills/resumes
  without persisting local loop state, derive "attempts already used" from
  BO-MCP **server truth**, not a local JSONL file: call
  `client.query_suggestions(campaign_id, limit=500)` and count entries whose
  `status != "pending"` (each `completed`/`rejected`/`expired` suggestion is
  one consumed attempt). This avoids the anti-pattern of reading a local
  provenance file back to decide whether to continue the loop, while still
  making the invocation budget resume-safe. `get_results()` alone
  undercounts because failed/rejected attempts never produce a result row.
- On resume, first check `client.query_suggestions(campaign_id,
  status_filter="pending", limit=500)` and evaluate any pending suggestions
  before calling `generate_suggestions` again — a prior invocation may have
  generated a batch and crashed before evaluating all of it.
- Failed oracle attempts should NOT be submitted as fake/sentinel BO-MCP
  results. Instead: record the failure in the local append-only JSONL
  artifact (for reporting only) and call
  `client.update_suggestion_status(suggestion_id, "rejected")` so the
  suggestion is retired without polluting the objective history; the
  failure still counts toward the attempt budget.
- `client.get_campaign(campaign_id)["status"]` is the right check before
  pausing at shutdown (`"running"` -> `lifecycle(action="pause")`); use
  `get_campaign`/`lifecycle(action="resume"/"reopen")` at the start of a
  resumed invocation based on the current status (`paused` -> resume,
  `completed` -> reopen).
- Final human-facing report should be rebuilt from BO-MCP's own
  `query_suggestions` (all, non-pending) joined with `get_results` (by
  `suggestion_id`) rather than from the local JSONL, so it's correct even if
  the local artifact file is lost — the JSONL is provenance only.
- `generate_suggestions(..., timeout_s=...)` accepts an explicit timeout;
  wiring the CLI's `--poll-s` into `timeout_s=max(poll_s*2, 120)` gives that
  flag genuine purpose since the oracle/BayBE loop here is fully
  synchronous (no separate async polling phase is needed for small discrete
  search spaces).
- `ValidateIntakeResponse` uses the key `"valid"` (bool), not `"success"`,
  for `client.validate_intake(...)`.
- `SuggestionStatusUpdateRequest.status` only accepts
  `"accepted"|"rejected"|"expired"` — never pass `"completed"` (that
  transition happens automatically when `submit_results` references the
  `suggestion_id`).
