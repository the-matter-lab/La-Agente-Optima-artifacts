# BO-MCP / PySCF campaign-script authoring notes

## BO-MCP API shapes (verified)
- `IntakeData` objective goal: use **either** `direction` **or** `target_mode` (mutually
  exclusive; `target_mode` enum: `minimize|maximize|match`). `unit` is display-only.
- `AcquisitionMethod` enum spelling is `noisy_expected_improvement` (not `noisy_ei`).
- Categorical params: `type="categorical"` + `categories` (>=2). Numeric grids:
  `type="discrete"` + `values` (fractional values allowed).
- BayBE per-parameter encoding goes in `parameter_options={"baybe": {"encoding": "OHE"}}`
  and validates fine; BayBE capability report lists only
  `categorical, mixed_search_space, multi_objective` as unconditional features.
- `generate_suggestions` response key is `suggestions`; each item has `suggestion_id`
  and `parameter_values`.
- `get_results` rows: `parameter_values` / `objective_values` dicts (plus `id`,
  `suggestion_id`, `created_at`).
- `update_suggestion_status` only accepts `accepted|rejected|expired` — never `completed`
  (that happens automatically when a result cites the suggestion_id) and there is no
  `failed` status. Use `rejected` for an attempted-but-failed evaluation.
- `lifecycle` actions: `pause|resume|terminate|reopen` (no `complete`).
- `next_action(...)` returns `status`/`iteration`/`n_results`/`action`/`reason`; branch on
  `action == "bo_generate_suggestions"`. Map `status` -> lifecycle action with
  `{"paused": "resume", "completed": "reopen"}` at the top of the loop so a re-run of the
  same entrypoint with `--campaign-id` resumes cleanly.
- Always `POST /api/v1/campaigns/validate` (client `validate_intake`) before creating —
  cheap and catches enum/field-shape mistakes.

## Script-structure caveats learned
- Seed the per-invocation "best so far" from `client.get_results(campaign_id)` at startup,
  otherwise a resumed invocation prints a best-so-far that is worse than the campaign best.
- Keep two record views when artifacts must survive resumes: append-only JSONL for the
  whole campaign, plus in-invocation records for per-invocation counts. Mirroring the JSONL
  into a JSON array is provenance, not loop state, so it does not violate the no-disk-loop-state rule.
- `configure_logfire()` + `logfire.instrument_requests()` writes its own console span lines
  to stdout; tagged `[EVENT]/[RESULT]/...` lines still pass a monitor regex filter, so no
  extra suppression is needed, but do not rely on stdout being tag-only.
- `curl` is not installed in the container — probe HTTP services with
  `uv run --project /app python -c "import requests; ..."` instead.
- Running a workspace script that imports repo packages needs `uv run --project /app python`
  when the CWD is not `/app`.
