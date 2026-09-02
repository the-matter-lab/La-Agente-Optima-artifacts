# 02 — Phosphine ligand electronic tuning

Reported in the main text table `computational-showcases` and in SI
`si:phosphine`.

A purely digital, multi-objective BO campaign over 364 monodentate phosphines
P(R¹)(R²)(R³), used as a ligand-level proxy for Ni catalysis after Laplaza et
al. (2022). Four objectives minimized jointly: HOMO error against −5.8 eV,
HOMO–LUMO gap error against 5.0 eV, molecular volume in excess of 350 Å³, and
heavy-atom count; phosphorus partial charge recorded as an auxiliary
descriptor. Evaluator: the Gráfico PySCF execution graph.

Budget 8 + 40 = 48 evaluations, all 48 successful. Hypervolume 0.791 → 1.038;
Pareto set 3 → 17. 33 orchestrator tool calls / 128 LLM calls; 6.18 M input /
50.4 k output tokens; $7.08.

The campaign deliberately produced no single best ligand: the electronic
objectives conflict, and the agent identified the steric objective as
uninformative and recommended stopping.

## Contents

- `gallery_guest_1785953700180-chat/` — conversation
  `019fd322-e98d-75ea-bd97-2d403617ff65`, main trace
  `019fd322e9ae83679caa41fcb820af41`, root span `6c3c5c561c6c3ff0`, 2026-08-05.
  `model_messages.json` holds 142 messages.
- `gallery_guest_1785953700180-workspace/` — agent working directory.
  - `artifacts/phosphine_electronics_20260805_182629/` is the cumulative
    campaign artifact set cited by the SI (earlier timestamped directories are
    partial runs from the same session).
  - `phosphine_paper_results_bundle_20260805/` is the agent-assembled results
    bundle.
  - `.grafico/execution_logs/` holds one log per PySCF execution-graph call.

BO-MCP campaign `f4e94d3d-0e06-43aa-baab-8bb15da9b843`.
