# 01 — Combinatorial molecular discovery for organic solid-state lasers

Reported in the main text, *Results → Digital discovery campaigns → Combinatorial
molecular discovery for organic solid-state lasers* (Fig. `osl_campaign`). There
is no dedicated SI section for this showcase.

A multi-objective, closed-loop BO campaign over the fragment catalogues of
Strieth-Kalthoff et al. (2024), assembled under an `A–B–C–B–A` composition rule
from cap, bridge, and core fragments. Objectives: maximize oscillator strength,
minimize colour error against a target visible excitation energy, minimize a
structural ambiguity penalty. Evaluation is a digital proxy — RDKit ETKDG/MMFF
conformer search followed by PySCF RKS PBE/3-21G single point and TDA-TDDFT for
the first three singlets.

Of 462 672 theoretically accessible combinations (42 caps, 68 bridges, 162
cores), Stage 0 restricted the space to 360 candidates; a frontier-aware
expansion widened it to 2592 for Stage 1. 38 successful observations in total.

## Contents

| Path | Chat room | What it is |
| --- | --- | --- |
| `gallery_guest_1782848407339/` | 1782848407339 (2026-06-30) | **Stage 0** — the 360-candidate "smallest fragments" campaign: driver and smoke-test scripts, runbook, fragment catalogues (`adk9227_data_s*.csv`), generated structures, run log, and campaign artifacts. Predecessor BO-MCP campaign `d661d8e6-34c2-476f-a065-4c485509e50f`, continued into a successor campaign seeded with its 6 completed results plus 10 new evaluations (16 observations total). |
| `gallery_guest_1783043406297_v1/` | 1783043406297 (2026-07-03) | **Stage 1 / 1b** — the expanded 2592-candidate campaign. Earlier snapshot of the workspace. |
| `gallery_guest_1783043406297_v2/` | 1783043406297 (2026-07-03) | **Stage 1 / 1b** — later snapshot of the same room, and the one to prefer: it adds `logfire_trace_exports/` (main plus four subagent message histories) and `latex_text.tex`. |
| `logfire_links.txt` | — | Logfire UI deep links to the four Stage 0 root traces (project `matterlab/bo-mcp-grafico`). |

Both Stage 1 snapshots are kept because neither is a superset of the other: `v1`
additionally holds three plot outputs (`*_modified.png`, two `.svg`) and three
plotting scripts (including two `.bu` backups) that `v2` does not.

Reported resource use for the whole showcase: 47 top-level turns over
3 d 22 h calendar time (16.0 h agent wall-clock), 397 LLM calls (137 main agent,
240 across four gpt-5.4 subagents, 20 gpt-4.1 one-shots), 35.4 M input /
229 k output tokens, $24.40.

## Provenance note

`gallery_guest_1782848407339/logfire_trace_exports/` was extracted from
`osl_small_fragments_chat_traces.zip` in the source archive. Unlike every other
archive in the OneDrive tree, that zip is **not** a duplicate of its unpacked
sibling: the unpacked directory lacks these 15 trace-export files. The rest of
the zip is byte-identical to the unpacked directory and was not copied twice.
