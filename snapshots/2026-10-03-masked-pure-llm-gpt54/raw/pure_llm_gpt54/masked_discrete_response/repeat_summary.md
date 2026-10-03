# BO-MCP Repeat Summary

- Run id: `fc6d6064-ff11-4549-9acc-788a1b4431db`
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
| openai-responses | openai-responses:gpt-5.4 | main_agent_llm_suggestion_no_bo | ['masked_discrete_response'] | 3 | 3 | 1 | 1 | 1 |  | 0.006334 | 2.596 | 3194 | {'not_applicable': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 3 | 3 | 1 | 1 | 0 | {'not_applicable': 3} | 1 | 1 | 60 | 59.67 | 155.8 | 1.916e+05 | 0.38 | 79.2 |  | 0 | 2.596 | 0.006334 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 60 | 60..60 | 59..60 | 0 | 79.2..79.2 |  |  |  |  |  | 3194 | 12.33 | 65.67 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 1.754e+05 | 1.617e+04 | 5886 | 1.338e+05 |  | 0 | 0 |  | {'evaluate_masked_discrete_response_value': 188, 'list_monitors': 5, 'start_monitor': 5} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 79.2 | 60 | 59 | 60 | 0 | matched | 142 | 1.035e+05 | 0.3313 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_001/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_002 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 79.2 | 60 | 60 | 60 | 0 | matched | 147.7 | 2.085e+05 | 0.3554 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_002/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_003 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 79.2 | 60 | 60 | 60 | 0 | matched | 177.6 | 2.628e+05 | 0.4534 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_003/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
