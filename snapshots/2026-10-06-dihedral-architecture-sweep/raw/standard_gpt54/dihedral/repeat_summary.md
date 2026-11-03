# BO-MCP Repeat Summary

- Run id: `dihedral-standard-aligned-baybe-litellm-gpt54-20261006T175326Z`
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
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | standard_subagent_script_bo_mcp | ['dihedral'] | 3 | 3 | 1 | 1 | 1 |  | 0.07837 | 54.47 | 6.648e+04 | {'verified': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | 3 | 3 | 1 | 1 | 1 | {'verified': 3} | 1 | 1 | 60 | 60 | 3268 | 3.989e+06 | 4.702 | -233.2 |  | 1.295e-08 | 54.47 | 0.07837 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | 60 | 60..60 | 60..60 | 0 | -233.2..-233.2 | -1.399e+04 | -233.2 | 0 | 0 | 1 | 6.648e+04 | 24.33 | 26.67 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | 3.952e+06 | 3.712e+04 | 1.615e+04 | 3.462e+06 |  | 3.408e+06 | 9.333 | 28 | {'bash_exec': 48, 'list_monitors': 20, 'start_monitor': 3, 'stop_monitor': 3, 'task': 3, 'wait_tasks': 3} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 3355 | 3.245e+06 | 4.951 | 7953a666-4383-4766-9fe2-4ca5b1bf8d1b |  | True | [] |
| repeat_002 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 3286 | 4.949e+06 | 5.046 | 119fc824-ea4a-4d83-b645-f3e7cec98ed2 |  | True | [] |
| repeat_003 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | standard_subagent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 3163 | 3.773e+06 | 4.11 | 5a88ba23-f731-4a2f-bef2-011d61841b55 |  | True | [] |
