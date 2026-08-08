# BO-MCP / PySCF campaign-script authoring notes

## BO-MCP intake (verified against live API)
- `acquisition_method` enum uses **full** names: `noisy_expected_improvement`,
  `expected_improvement`, `upper_confidence_bound`, `probability_of_improvement`,
  `posterior_mean`, `simple_regret`, `hypervolume_improvement`, ... — the short alias
  `noisy_ei` is rejected with HTTP 422.
- BayBE backend accepts per-parameter `parameter_options: {"baybe": {"encoding": "OHE"}}`
  on categoricals and `backend_options: {"baybe": {"recommender": {"switch_after": N,
  "bayesian": {"n_restarts": .., "n_raw_samples": ..}}}}`; `initial_design_size` alone is
  enough to get a space-filling warmup phase.
- `type: "discrete"` + `values: [...]` keeps fractional grids exactly (e.g. 0.057/0.1/0.153).
- `validate_intake` returns `{"valid": true, "errors": [], "warnings": []}`; capability probe
  is `GET /api/v1/capabilities?backend=baybe`.
- `update_suggestion_status` only accepts `accepted` / `rejected` / `expired` (not `failed`).
- `submit_results` duplicate rejection raises `BoMcpOperationError`; retry with `force=True`
  under a **fresh** idempotency key (force is part of the idempotency hash).
- Suggestion records from `generate_suggestions` carry `suggestion_id` + `parameter_values`;
  response also has `iteration`.

## Script patterns that worked
- Snap suggestion numerics back onto the declared grid before calling an external oracle
  (nearest-value helper); avoids float drift rejections by strict services.
- Keep the attempt artifact as append-only JSONL, and build the JSON array snapshot + final
  report by re-reading the JSONL at the end (reporting only — never for loop decisions).
- Check the stop file both at startup (before resume/create) and at the top of each iteration.
- Reuse the smoke-test campaign for the real run and subtract already-recorded attempts from
  the CLI attempt budget so the user's total-evaluation budget stays exact.
