# BO-MCP Repeat Summary

- Run id: `dihedral-localbo-aligned-baybe-litellm-gpt54-20261006T143026Z`
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
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | main_agent_script_no_bo_mcp | ['dihedral'] | 3 | 3 | 1 | 1 | 1 |  | 0.01632 | 42.07 | 2.185e+04 | {'not_applicable': 3} | no BO-MCP campaign trace/diagnostics |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | 3 | 3 | 1 | 1 | N/A | {'not_applicable': 3} | 1 | 1 | 60 | 60 | 2524 | 1.311e+06 | 0.9793 | -233.2 |  | 4.913e-06 | 42.07 | 0.01632 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | 60 | 60..60 | 60..60 | 0 | -233.2..-233.2 | N/A | N/A | N/A | N/A | N/A | 2.185e+04 | 29.67 | 40.67 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | 1.29e+06 | 2.1e+04 | 7770 | 1.138e+06 |  | 0 | 6.333 | 19 | {'bash_exec': 94, 'container_execute': 5, 'load_skill': 3, 'python_repl': 14, 'read_skill_resource': 6} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | True | True | not_applicable | -233.2 | 60 | 60 | 60 | 0 | matched | 2457 | 9.262e+05 | 0.9197 | /local-scratch/home/lynnfang00/research/dihedral-runs-sweep-2026-10-06b/dihedral_localbo_aligned_baybe_litellm_gpt54_20261006T143026Z/repeat_001/cases/dihedral/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_002 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | True | True | not_applicable | -233.2 | 60 | 60 | 60 | 0 | matched | 2756 | 1.716e+06 | 1.129 | /local-scratch/home/lynnfang00/research/dihedral-runs-sweep-2026-10-06b/dihedral_localbo_aligned_baybe_litellm_gpt54_20261006T143026Z/repeat_002/cases/dihedral/workspace/bo-mcp-eval/local_results.json |  | True | [] |
| repeat_003 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_script_no_bo_mcp | True | True | not_applicable | -233.2 | 60 | 60 | 60 | 0 | matched | 2361 | 1.29e+06 | 0.8894 | /local-scratch/home/lynnfang00/research/dihedral-runs-sweep-2026-10-06b/dihedral_localbo_aligned_baybe_litellm_gpt54_20261006T143026Z/repeat_003/cases/dihedral/workspace/bo-mcp-eval/local_results.json |  | True | [] |
