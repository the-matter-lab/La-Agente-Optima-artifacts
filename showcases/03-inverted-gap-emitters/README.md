# 03 — Singlet–triplet gap search over the Pollice 2021 library

Reported in the main text table `computational-showcases` (as "Inverted-gap
emitters") and in SI `si:pollice`.

A single-objective, fixed-library BO campaign to find the molecule with the
smallest TD-DFT singlet–triplet gap in a size-filtered 1512-molecule subset of
the INVEST candidate set of Pollice et al. (2021). Each evaluation is a
conformer search followed by an excited-state calculation. Published reference
values were withheld from the agent, so both its candidate selection and the
accuracy of its cheap evaluator can be measured.

44 evaluations attempted, 39 successful. Best gap 0.227 → 0.223 eV — a small
improvement, because the first of five randomly sampled seed molecules was
already near-optimal. 34 orchestrator tool calls / 279 LLM calls; 13.1 M input /
76.5 k output tokens; $13.01.

Before launching, the agent timed a trial evaluation and switched to a cheaper
method and smaller budget when server timings showed its runtime estimate was
too optimistic. A post-campaign comparison against the published references
showed the cheap TD-DFT evaluator ranked the evaluated molecules well but did
not reproduce their inverted gaps.

## Contents

- `gallery_guest_1785801755289-chat/` — conversation
  `019fca17-1a4f-7724-92ed-deb3245cc652` (subagent conversation
  `2127825d0134423ba32b7de0b8a0ef1f`), 2026-08-04/05. `model_messages.json`
  holds 272 messages.
- `gallery_guest_1785801755289-workspace/` — agent working directory.
  - `pollice_lowest_conformer_gap_artifacts/` is the cumulative campaign
    artifact set: BO export, campaign intake, evaluation results, run and
    continuation logs, per-molecule worker logs, improvement-curve plots.
  - `pollice_lowest_conformer_gap_reproduction_20260805/` is the
    agent-assembled reproduction bundle.
  - `pollice_2021_geometry_available.csv` is the input candidate table. Its
    `delta_est_mean_ev` column carries the aggregated published benchmark
    values quoted for comparison in the SI; these are not new calculations.

BO-MCP campaign `f023cf90-a1a1-470a-987d-134a38919812`.
