# 05 — Xe/Kr MOF design over PORMAKE and Zeo++

Reported in the main text table `computational-showcases` (as "Xe/Kr MOFs") and
in SI `si:mof`.

A small-budget BO campaign following the design goal of Lim et al. (2021), with
their GCMC-derived selectivity objective replaced by a geometric proxy that
requires no adsorption simulation. Candidates are assembled with PORMAKE and
their pore geometry analyzed with Zeo++.

Two campaigns, in sequence. The first treated topology, node, and edge as
independent variables — 2800 nominal combinations of which only 420 were valid —
and mostly proposed unconstructible frameworks. Rather than spend more budget on
that representation, the agent rebuilt the problem as a finite set of
connectivity-compatible triples (109 valid candidates) and carried all prior
successes forward as evidence.

Budget 30 + 50 = 80 evaluations, 65 successful. Desirability 0.487 → 0.502;
Pareto set 7 → 12. 25 orchestrator tool calls / 162 LLM calls; 11.6 M input /
61.3 k output tokens; $11.44. The improvement is modest; the reported capability
is that the agent identified the search-space representation, not the optimizer,
as the bottleneck.

## Contents

- `gallery_guest_1786548193992-chat/` — main conversation
  `019ff692-76ed-7714-9180-fdb22fe00d32` (bo-pyscf-specialist conversation
  `de59c2acfc404300aad19ba5857d8cd6`), 2026-08-12 15:23–16:44 UTC.
  `model_messages.json` holds 156 messages. Root trace of the first campaign:
  `019ff692770c44d4079622e891d666e8`; of the refined follow-up:
  `019ff6cd4c3a43c396e157f369bfc60d`.
- `gallery_guest_1786548193992-workspace/` — agent working directory.
  - `xe_kr_mof_bo/` is the agent-authored campaign package.
  - `run_xe_kr_mof_bo.py`, `continue_xe_kr_mof_bo_refined.py` and the two
    `HOW_TO_EXECUTE_*.md` runbooks are the entry points for the first and the
    refined campaign.
  - `xe_kr_mof_bo_artifacts/<timestamp>/` holds per-run campaign exports,
    candidate spaces, evaluation records, validation reports, generated `.cif`
    frameworks, and improvement-curve plots.

BO-MCP campaigns `fe6e1020-d1e6-417e-ad5f-afa1cdf3ac5e` (first) and
`c3e99bc8-1aef-4487-9db5-318a7c4c2c16` (refined).
