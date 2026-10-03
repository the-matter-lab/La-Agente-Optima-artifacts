# BO-MCP Repeat Summary

- Run id: `38d9544e-0bda-4e7e-aeac-3b13064a3270`
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
| openai-responses | openai-responses:gpt-5.4 | main_agent_llm_suggestion_no_bo | ['masked_discrete_response'] | 3 | 3 | 1 | 1 | 1 |  | 0.005912 | 2.439 | 3203 | {'not_applicable': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 3 | 3 | 1 | 1 | 0 | {'not_applicable': 3} | 1 | 1 | 60 | 60 | 146.3 | 1.922e+05 | 0.3547 | 76.89 |  | 10.62 | 2.439 | 0.005912 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 60 | 60..60 | 60..60 | 0 | 72.28..79.2 |  |  |  |  |  | 3203 | 11.67 | 68.33 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | 1.776e+05 | 1.458e+04 | 4899 | 1.369e+05 |  | 0 | 0 |  | {'evaluate_masked_discrete_response_value': 193, 'list_monitors': 6, 'start_monitor': 6} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 79.19 | 60 | 60 | 60 | 0 | matched | 133.5 | 1.747e+05 | 0.3247 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_001/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_002 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 79.2 | 60 | 60 | 60 | 0 | matched | 146.2 | 2.043e+05 | 0.3603 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_002/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_003 | openai-responses | openai-responses:gpt-5.4 | masked_discrete_response | main_agent_llm_suggestion_no_bo | True | True | not_applicable | 72.28 | 60 | 60 | 60 | 0 | matched | 159.3 | 1.975e+05 | 0.3792 | /app/eval-output/masked_discrete_response_pure_llm_gpt54_3x/repeat_003/cases/masked_discrete_response/workspace/bo-mcp-eval/local_results.json |  | True | [] |
