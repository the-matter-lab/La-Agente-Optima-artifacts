# 07 — Multi-objective flow photochemistry on RoboChem-Flex

Reported in the main text, *Results → Multi-objective flow photochemistry with
RoboChem-Flex* (Fig. `robochemflex`), and in SI `si:robochemflex:trace` (cleaned
operator/agent transcript), `si:robochemflex:cost` (cost and resource
accounting), `si:robridge` (the RoBridge platform service), and
Tab. `robochemflex-runs` (the 23 experiments in figure order).

A physical, multi-objective closed-loop campaign on the RoboChem-Flex segmented
flow platform, reached through *RoBridge* — an authenticated, stateful HTTP
service on the robot computer that holds platform and safety state while
optimizer state stays in BO-MCP. Objectives: reaction yield (primary) and an
agent-defined green metric (secondary). Search space: photocatalyst and oxidant
identity, catalyst / TFAA / oxidant equivalents, light intensity (restricted by
RoBridge's capability descriptors to {0, 25, 50, 75, 100} %) and residence time
(2–90 min), at a fixed 650 µL slug and 100 mM substrate.

23 experiments were executed (`R0044`–`R0076`), consuming 313 mg substrate,
1.87 mg photocatalyst, 488 mg TFAA and 227 mg oxidant, and 18.2 h of reactor and
¹⁹F NMR time. Best yield 58.81 % at `R0067`. Experiments 1–21 were carried into
a reseeded yield-only campaign as history; 22–23 were measured in it.

## Contents

The campaign ran in two sessions. Session 1 ran on the original workstation;
session 2 continued the same campaign in a copy of the session-1 workspace after
that machine had to be replaced.

| Path | What it is |
| --- | --- |
| `gallery_guest_1784900563933-chat/` | **Session 1** conversation `ffe7e623-ede6-445d-be67-8b363c87b2fc`, room created 2026-07-24. `model_messages.json` holds 398 messages — the count the SI transcript was generated from. |
| `gallery_guest_1784900563933-workspace/` | **Session 1** agent working directory: campaign package, chemical-space CSV inputs, campaign and run logs, artifacts. |
| `gallery_guest_1784953742092-20260729-chats/` | **Session 2** conversation `513305b8-d434-42a5-a324-85f3b18d33d5`, room created 2026-07-25, exported 2026-07-29. `model_messages.json` holds 576 messages — again the count the SI transcript was generated from. |
| `gallery_guest_1784953742092-20260729/` | **Session 2** agent working directory as of the 2026-07-29 export: the reseeded yield-only campaign, retry continuation scripts, campaign logs, search-space coverage plots, artifacts. |
| `cost_export_20260805/` | The cost and resource accounting export. `roboflex_runs_in_figure.csv` is the direct source of Tab. `robochemflex-runs`; also `roboflex_runs_submitted.csv`, `roboflex_campaign_summary.csv`, `roboflex_reagents.csv`, and a `README.md` describing them. |

Session 2 was archived twice in the source tree: a 2026-07-25 export (326
messages, 443 workspace files) and the 2026-07-29 export kept here (576
messages, 783 workspace files). The later export is a strict superset of the
earlier workspace and matches the message count the SI cites, so only it was
copied.

## Why the run IDs start at R0042

`cost_export_20260805/roboflex_runs_submitted.csv` covers `R0028`-`R0080`, but
the reported campaign begins at `R0042`. Runs `R0028`-`R0041` come from an
exploratory session on 23-24 July that preceded this campaign in a different
package and BO campaign; none of its code, files, or measurements were carried
forward, and the SI does not reproduce it. Its rows are retained in the cost
export only so that total material spent in the lab can be reconstructed - that
directory's own `README.md` separates the phases. No agent conversation or
workspace for that session is included here.

Lab photographs and screenshots of the platform that sat alongside these runs
were also left out; they are figure source material, not run data.
