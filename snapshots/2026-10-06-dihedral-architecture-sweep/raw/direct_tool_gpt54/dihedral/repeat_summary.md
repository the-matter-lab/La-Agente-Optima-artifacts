# BO-MCP Repeat Summary

- Run id: `dihedral-toolloop-aligned-baybe-litellm-gpt54-20261006T131917Z`
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
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | main_agent_tool_passing_bo_mcp | ['dihedral'] | 3 | 3 | 1 | 1 | 1 |  | 0.0502 | 22.96 | 9.998e+04 | {'verified': 3} |  |

| Provider | Model | Case | Architecture | Runs | Clean runs | Task success | Clean evidence | Verification/fallback | Verification statuses | Arch contract | Budget match | Attempts mean | Successes mean | Runtime mean | Total tokens mean | Cost mean | Clean best mean | Norm best | Best variance | Clean sec/eval | Clean cost/eval | Failures |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | 3 | 3 | 1 | 1 | 1 | {'verified': 3} | 1 | 1 | 60 | 60 | 1378 | 5.999e+06 | 3.012 | -233.2 |  | 9.358e-08 | 22.96 | 0.0502 | {} |

## Optimization And Efficiency

| Provider | Model | Case | Architecture | Budget | Attempts range | Successes range | Budget delta mean | Clean best range | Clean raw BO AUC mean | Clean BO AUC/attempt mean | Duplicate rate | Failed eval rate | Clean convergence rate | Clean tokens/eval | Requests mean | Tool calls mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | 60 | 60..60 | 60..60 | 0 | -233.2..-233.2 | -1.399e+04 | -233.2 | 0 | 0 | 1 | 9.998e+04 | 64 | 123 |

## Token And Tool Diagnostics

| Provider | Model | Case | Architecture | Input tokens mean | Output tokens mean | Reasoning tokens mean | Cache read mean | Main tokens mean | Subagent tokens mean | Script count mean | Script diversity | Tool calls by name | Mode violations |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | 5.947e+06 | 5.213e+04 | 6852 | 5.616e+06 |  | 0 | 0.6667 | 2 | {'bo_create_campaign': 3, 'bo_export_campaign': 3, 'bo_generate_suggestions': 22, 'bo_get_diagnostics': 4, 'bo_health_check': 3, 'bo_list_capabilities': 3, 'bo_list_results': 3, 'bo_list_suggestions': 1, 'bo_submit_results': 23, 'bo_terminate_campaign': 3, 'bo_validate_intake': 3, 'container_execute': 82, 'container_read_file': 8, 'container_write_file': 16, 'inspect_smiles_geometry': 3, 'load_skill': 3, 'read_skill_resource': 6, 'set_molecular_dihedrals': 180} | {} |

## Repeat Runs

| Repeat | Provider | Model | Case | Architecture | Task success | Clean evidence | Verification status | Best | Attempts | Successes | Budget | Budget delta | Budget status | Runtime | Tokens | Cost | Campaign/local artifact | Failure | Contract | Violations |
| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| repeat_001 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1409 | 5.389e+06 | 2.974 | ac6fa337-27d4-49ba-a935-f403ca6e16d1 |  | True | [] |
| repeat_002 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1342 | 5.694e+06 | 2.939 | 91ee3992-0404-462e-9c01-37ce79f5e6d0 |  | True | [] |
| repeat_003 | litellm-openai-responses | litellm-openai-responses:gpt-5.4 | dihedral | main_agent_tool_passing_bo_mcp | True | True | verified | -233.2 | 60 | 60 | 60 | 0 | matched | 1381 | 6.913e+06 | 3.123 | 9dc539eb-897b-4b7f-9cd0-c4ae87683e55 |  | True | [] |
