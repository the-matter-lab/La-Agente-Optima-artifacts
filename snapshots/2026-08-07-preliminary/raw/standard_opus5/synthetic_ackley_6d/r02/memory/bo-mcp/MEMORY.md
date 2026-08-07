## BO/PySCF campaign-script authoring caveats (general)

- **Logfire console duplication**: `configure_logfire()` enables a console exporter, so every
  `logfire.info/debug` line is echoed to stdout and duplicates the script's own tagged prints.
  For monitor-friendly stdout use `configure_logfire(console=False)` in the entrypoint header,
  before importing the campaign package.
- **Logfire dynamic messages**: `logfire.info(msg)` / `logfire.debug(msg)` with a preformatted
  string containing `{...}` raises `FormattingFailedWarning`. Pass a template instead:
  `logfire.debug("{message}", message=msg)`.
- **BO-MCP `GET /api/v1/campaigns/{id}`** returns a *flat* campaign object
  (`id`, `spec_id`, `name`, `status`, `iteration`, `created_at`, `n_parameters`, ...). There is no
  nested `"campaign"` key, so `resp.get("campaign") or resp` is the safe accessor; reading
  `resp["campaign"]["status"]` silently yields empty and breaks the end-of-run pause.
- **BayBE intake that validates cleanly**: `backend="baybe"`, continuous params as
  `{"name":..., "type":"continuous", "bounds":{"lower":0.0,"upper":1.0}}`,
  objective `{"name":..., "direction":"maximize", "unit":...}`,
  plus `acquisition_method="expected_improvement"`, `batch_size`, `initial_design_size`,
  `random_seed`. Leave `max_iterations`/`max_observations` unset (immutable cap).
- Suggestions come back as `resp["suggestions"]` with `suggestion_id` + `parameter_values`;
  submit results with the same `suggestion_id` and `objective_values`.
- Nested same-quote f-strings (`f"{f'{x:.2f}' ...}"` reusing `'` inside `'`) only parse on
  Python 3.12+; compute the formatted sub-strings first to stay portable.
