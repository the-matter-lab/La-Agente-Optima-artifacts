# Masked benchmarks — pure-LLM arm (GPT-5.4, 3 repeats)

Protocol cells for `main_agent_llm_suggestion_no_bo` on masked Ackley surface and
masked discrete-response benchmarks. Generated 2026-10-03 from Grafico eval harness
(akg4pyscf `c0809061`).

Arm directory: `raw/pure_llm_gpt54/` (`pure_llm_gpt54` = pure in-context LLM suggestions, no BO-MCP).

| Case | Repeats | Trimmed artifacts per cell |
|------|---------|----------------------------|
| `masked_surface_6d` | r01–r03 | summary, manifest, metrics, prompt, local_results |
| `masked_discrete_response` | r01–r03 | same |

Full conversations remain on the goethe workstation under `outputs/bo_mcp_evals/issue61_gpt54/`.
