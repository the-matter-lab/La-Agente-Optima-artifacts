## BO-MCP script-authoring notes (from synthetic Ackley-6D campaign)

- `BoMcpClient.get_campaign(campaign_id)` exists (not just create/next_action/etc.)
  and is the way to check current `status` ("running"/"paused"/"completed")
  before deciding whether to pause at shutdown, or whether to resume/reopen
  when a `--campaign-id` is passed in.
- `BoMcpClient.make_idempotency_key(prefix, *parts)` appends a fresh random
  uuid suffix on every call — call it ONCE per logical attempt and reuse the
  returned string for retries of that exact same payload; do not call it
  again for the "same" attempt (that mints an unrelated key).
- `client.get_results(campaign_id)` rows only carry
  `{id, campaign_id, suggestion_id, parameter_values, objective_values,
  source, submitted_by, measurement_uncertainty, created_at}` — no
  `metadata` field is echoed back, so anything stashed in
  `ResultCreate.metadata.notes` (e.g. an extra derived value like a raw,
  pre-normalization objective) cannot be read back from the server. If a
  derived quantity is needed in the final report and the mapping from
  parameters -> that quantity is deterministic, just recompute it locally
  from `parameter_values` instead of round-tripping it through metadata.
- For counting "attempted" evaluations (successes + evaluation failures)
  without any local/persisted loop counter: `len(client.get_results(cid))`
  gives successes; failures that were never submitted (evaluator raised)
  should be marked via `client.update_suggestion_status(suggestion_id,
  "rejected")`, and `len(client.query_suggestions(cid,
  status_filter="rejected"))` gives the failed-attempt count. Sum of the two
  is a server-derived attempted-count that works correctly across resumed
  invocations without writing any progress file to disk.
- `SuggestionStatusUpdateRequest` only accepts `status` (accepted/rejected/
  expired) — there is no free-text reason field on that endpoint. If a
  human-readable failure reason must survive across resumed invocations,
  it has to live in the local append-only artifact (CSV/JSONL), not on the
  server; that's fine for reporting since only continue/stop decisions must
  come from the server, not the row-level detail.
- Duplicate-coordinate submission rejection pattern that works well: try
  `submit_results(..., force=False)` first; if `success` is false, retry the
  same payload with `force=True` under a brand-new idempotency key (reusing
  the key that produced the rejection returns a 409 idempotency conflict,
  since duplicate rejections are cached as terminal).
- A plain synthetic/deterministic objective (no chemistry) still integrates
  cleanly with the standard BO-MCP loop skeleton from the client docstring;
  no PySCF/CREST-specific tooling is needed — just BoMcpClient calls plus a
  campaign-agnostic `evaluation.run_candidate(evaluate_fn, params)` harness
  that never raises (mirrors the pattern used for chemistry evaluators, but
  parallelization/timeout wrapping is unnecessary when evaluation is a pure
  closed-form function).

## BO-MCP artifact-integrity lesson (Ackley-6D repair, 2nd invocation)

- Root cause of a real local-artifact gap: local results.csv/jsonl are only
  ever written by the campaign loop's own `reporting.append_row` call. Any
  result submitted to a campaign out-of-band (e.g. ad-hoc
  `client.submit_results(...)` calls made while interactively smoke-testing
  intake/suggestion/submit shapes *before* wiring up the real script) lands
  on the BO-MCP server (shows up in `get_results`) but is never mirrored
  locally, silently producing a local artifact with fewer rows than the
  server's attempted count even though the final stdout summary (which is
  correctly derived from server state) reports the right totals.
- Fix pattern: add a small `recovery.py` module (+ thin
  `recover_<slug>.py` CLI) that treats the server as sole source of truth —
  `get_results` for successes + `query_suggestions(status_filter=
  "rejected")` for failures, merge-sort by each record's `created_at`, and
  assign `evaluation_index` 1..N from that chronological order — then
  atomically overwrite (temp file + `Path.replace`) the local CSV/JSONL.
  This script must stay read-only against campaign lifecycle (no
  create/resume/reopen/pause, no submissions) so it's safe to run anytime,
  repeatedly, even against a `completed`/`paused` campaign.
- Recovering a derived field the server never echoes back (e.g. a raw
  pre-normalization value not present in `objective_values`) is easy when
  the mapping from `parameter_values` is a pure deterministic function:
  just recompute it locally in the recovery script instead of trying to
  round-trip it through result metadata (metadata isn't returned by
  `get_results` at all — see the earlier note on that).
- Cheap regression guard worth adding directly to the live campaign loop:
  at end-of-invocation, compare local JSONL line count against the
  server-derived attempted count (successes + rejected) and print an
  `[ALERT]` with the exact recovery command if they ever diverge again —
  catches this class of drift immediately instead of only at final
  reporting/audit time, without adding any local progress/loop-control
  state.
- Practical smoke-testing implication: when interactively probing BO-MCP
  request/response shapes for a new campaign package (validate_intake /
  create_campaign / generate_suggestions / submit_results) before the real
  script exists, either (a) do it against a disposable scratch campaign
  that gets discarded, or (b) immediately follow up by running the actual
  entrypoint against that same campaign so its own artifact-writing loop
  captures every result from the start — don't leave a real result
  submitted through an ad-hoc call as the only source for that data.
