# 04 — Agent-to-agent Co(II) bisphosphine tuning

Reported in the main text table `computational-showcases` (as "Co
bisphosphines") and in SI `si:cobalt`.

A digital, multi-objective campaign over 144 cationic Co(II) bisphosphine
hydroformylation catalysts, recast from Hood et al. (2020) as a finite
multi-objective search. This is the one showcase in which Óptima owned neither
the molecular structures nor the optimizer state: every three-dimensional
[Co(acac)(P₂)]⁺ structure was requested from *El Agente Estructural* over the
agent-to-agent interface, optimizer state stayed in BO-MCP, and evaluation was
an unrestricted DFT geometry optimization on the Gráfico PySCF execution graph.

Budget 4 + 10 = 14 evaluations, 6 feasible. Feasible-only hypervolume
0.572 → 1.000. 94 orchestrator tool calls / 557 LLM calls; 56.1 M input /
210 k output tokens; $53.29 — the most expensive of the four finite-space
campaigns, because each evaluation requires a metal complex to be built from a
textual ligand description before any electronic structure can be computed.

Faced with eight failed evaluations, the agent separated computational failure
from evidence about ligand performance, traced most failures to unconverged
geometry optimizations, and concluded that better starting structures and
relaxation protocol — not more BO iterations — were the right next step.

## Contents

- `gallery_guest_1786039292184-chat/` — conversation
  `5c85708c-0e94-44c4-8d1e-aac5f4997af5`, Logfire project `bo-mcp-grafico`,
  2026-08-06 to 2026-08-11. `model_messages.json` holds 408 messages.
- `gallery_guest_1786039292184-workspace/` — agent working directory.
  - `hood_co_bisphosphine_bo/` is the agent-authored campaign package.
  - `hood_co_bisphosphine_artifacts_pbe_converged/` holds the final campaign
    artifacts.
  - `.grafico/execution_logs/` holds one log per PySCF execution-graph call.

BO-MCP campaign `62fb243b-265e-4ba4-b5a8-d97e414fce2f`.
