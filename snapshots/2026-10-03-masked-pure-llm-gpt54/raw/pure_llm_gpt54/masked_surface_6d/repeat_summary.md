# BO-MCP Repeat Summary

- Run id: `e8031d4d-7105-457f-b563-cc0f0d9cf707`
- Total case runs: `3`
- Overall task pass rate: `1.0`
- Overall clean benchmark rate: `1.0`

## Definitions

- `Task success`: the agent run completed and produced a final answer.
- `Clean benchmark evidence`: the run satisfied the architecture contract, objective evidence was verified or fallback-verified, the evaluation budget matched, and a best objective was parsed.
- Primary objective, AUC, convergence, and per-evaluation efficiency statistics use only explicitly clean runs. Reliability, failure, budget, and total-resource statistics retain all requested runs.
- `Verification/fallback`: BO-MCP campaign/results verification, or an explicitly labeled fallback when diagnostics readback failed.
- `Budget match`: attempted objective evaluations matched the case's expected evaluation budget.
- `Attempts` and `successes`: attempted objective evaluations and successful objective values, not LLM retries or tool calls.
- `Convergence rate`: fraction of BO repeats whose BO diagnostics reported convergence; `N/A` for no-BO baselines.

## Interpretation

Preliminary interpretation: this within-architecture variance report should be read from pass/contract rate first, then completed evaluations, best-objective spread, runtime/cost efficiency, and repeat-level failures.
Limitations: this report summarizes observed eval traces, not a final scientific benchmark claim. Total case runs: `3`; cases: `[]`.

## Model Architecture Aggregate

| Provider | Model | Architecture | Cases | Runs | Clean runs | Task success | Clean evidence | Budget match | Mean normalized objective | Clean cost/eval | Clean sec/eval | Clean tokens/eval | Verification statuses | Issues |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| openai-responses | openai-responses:gpt-5.4 | main_agent_llm_suggestion_no_bo | ['masked_surface_6d'] | 3 | 3 | 1 | 1 | 1 |  | 0.006254 | 2.388 | 2872 | {'not_applicable': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | 3 | 3 | 1 | 1 | 0 | {'not_applicable': 3} | 1 | 1 | 60 | 60 | 143.3 | 1.723e+05 | 0.3753 | 0.4321 |  | 0.02413 | 2.388 | 0.006254 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | 60 | 60..60 | 60..60 | 0 | 0.2201..0.5878 |  |  |  |  |  | 2872 | 9.333 | 63.33 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | 1.564e+05 | 1.589e+04 | 4094 | 1.13e+05 |  | 0 | 0 |  | {'evaluate_masked_surface_6d': 180, 'list_monitors': 5, 'start_monitor': 5} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 0.4886 | 60 | 60 | 60 | 0 | matched | 160.3 | 2.082e+05 | 0.4265 | /app/eval-output/masked_surface_6d_pure_llm_gpt54_3x/repeat_001/cases/masked_surface_6d/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_002 | openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 0.2201 | 60 | 60 | 60 | 0 | matched | 128 | 1.164e+05 | 0.3157 | /app/eval-output/masked_surface_6d_pure_llm_gpt54_3x/repeat_002/cases/masked_surface_6d/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_003 | openai-responses | openai-responses:gpt-5.4 | masked_surface_6d | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 0.5878 | 60 | 60 | 60 | 0 | matched | 141.5 | 1.924e+05 | 0.3836 | /app/eval-output/masked_surface_6d_pure_llm_gpt54_3x/repeat_003/cases/masked_surface_6d/workspace/bo-mcp-eval/local_results.json |  | True | [] |
