# BO-MCP Repeat Summary

- Run id: `dihedral-mainscript-aligned-baybe-litellm-gpt54-20261006T163713Z`
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
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | main_agent_script_bo_mcp | ['dihedral'] | 3 | 3 | 1 | 1 | 1 |  | 0.02801 | 25.14 | 5.151e+04 | {'verified': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | 3 | 3 | 1 | 1 | 1 | {'verified': 3} | 1 | 1 | 60 | 60 | 1509 | 3.091e+06 | 1.681 | -233.2 |  | 1.412e-07 | 25.14 | 0.02801 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | 60 | 60..60 | 60..60 | 0 | -233.2..-233.2 | -1.399e+04 | -233.2 | 0 | 0 | 1 | 5.151e+04 | 40 | 45.33 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | 3.064e+06 | 2.642e+04 | 1.196e+04 | 2.834e+06 |  | 0 | 5.333 | 16 | {'bash_exec': 108, 'bo_get_diagnostics': 2, 'bo_health_check': 2, 'bo_list_capabilities': 2, 'bo_resume_campaign': 2, 'bo_submit_results': 3, 'inspect_bo_mcp_openapi_operation': 7, 'inspect_bo_mcp_openapi_overview': 3, 'load_skill': 3, 'python_repl': 4, 'read_skill_resource': 6} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1616 | 2.472e+06 | 1.603 | 5eef40c6-e45a-4768-9296-bfb3461330f6 |  | True | [] |
| repeat_002 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1412 | 2.752e+06 | 1.326 | 8cafd938-c084-42c0-bfa2-0c91f166ba35 |  | True | [] |
| repeat_003 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1497 | 4.048e+06 | 2.113 | 7955ebd5-dc25-40a7-a3b4-a91f93dd368e |  | True | [] |
