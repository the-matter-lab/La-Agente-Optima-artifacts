## BO-MCP Campaign Script Authoring

### BoMcpClient API Signatures
- `generate_suggestions(campaign_id, *, batch_size=1, timeout_s=...)` — does NOT accept `idempotency_key`
- `submit_results(campaign_id, *, results, idempotency_key, force=False)` — REQUIRES `idempotency_key`
- `update_suggestion_status(suggestion_id, status)` — positional args, status is second positional
- `lifecycle(campaign_id, *, action)` — keyword-only `action`
- `create_campaign(intake, idempotency_key=...)` — accepts `idempotency_key`
- `validate_intake(intake)` — no idempotency key

### Acquisition Method Values
The API expects lowercase enum values like `"expected_improvement"`, not `"EXPECTED_IMPROVEMENT"`. The valid values are listed in the OpenAPI schema enum for `AcquisitionMethod`.

### Ackley Function Normalization
When normalizing the Ackley function, the optimum (at z_i=0, x_i=0.5) can give `surface_response > 1` if the normalization range doesn't cover the optimum. This is expected behavior — the normalization maps the worst point to 0 and a reference point to 1, but the optimum can exceed 1.

### Package Structure
Campaign code should be a small package with one module per concern:
- `search_space.py` — parameter definitions
- `intake.py` — campaign intake construction
- `evaluator.py` — objective function evaluation
- `orchestrator.py` — BO-MCP loop
- `reporting.py` — result extraction, artifact writing, final report
- `__init__.py` — re-exports

The entrypoint (`run_*.py`) should be thin CLI/config wiring.