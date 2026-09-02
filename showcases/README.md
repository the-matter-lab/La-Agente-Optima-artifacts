# Showcase raw data

Raw run evidence for the seven **showcase campaigns** reported in *La Agente
Óptima: Towards Agentic Self-Driving Laboratories*.

Scope: for each showcase, the exported agent conversation and the agent's
working directory — the campaign packages it authored, its run logs, BO-MCP
exports, evaluation records, generated structures, and plots. Session screen
recordings, tool caches, and figure source material are not part of the run
record and are not included.

This tree is independent of `snapshots/`, which holds the **framework-comparison
benchmark** (66 evaluation cells across 11 arms). Nothing here is used by the
benchmark report, its figures, or `scripts/rebuild_figures.py`, and no file in
`snapshots/` was touched to add it. The two trees are only siblings in the same
repository.

## Contents

| Directory | Showcase | Reported in |
| --- | --- | --- |
| `01-osl-combinatorial-discovery/` | Combinatorial molecular discovery for organic solid-state lasers | Main text, *Digital discovery campaigns*; Fig. `osl_campaign` |
| `02-phosphine-ligand-electronics/` | Phosphine ligand electronic tuning (364 ligands) | Main text table `computational-showcases`; SI `si:phosphine` |
| `03-inverted-gap-emitters/` | Singlet–triplet gap search over the Pollice 2021 INVEST library (1512 molecules) | Main text table `computational-showcases`; SI `si:pollice` |
| `04-cobalt-bisphosphine-a2a/` | Agent-to-agent Co(II) bisphosphine tuning (144 ligands) | Main text table `computational-showcases`; SI `si:cobalt` |
| `05-xe-kr-mof-design/` | Xe/Kr MOF design over PORMAKE/Zeo++ | Main text table `computational-showcases`; SI `si:mof` |
| `06-raise-contact-angle/` | Closed-loop contact-angle matching on the RAISE platform | Main text, *Closed-loop formulation optimization with RAISE*; SI `si:raise` |
| `07-robochemflex-flow-photochemistry/` | Multi-objective flow photochemistry on RoboChem-Flex | Main text, *Multi-objective flow photochemistry with RoboChem-Flex*; SI `si:robochemflex:trace`, `si:robochemflex:cost`, `si:robridge`, Tab. `robochemflex-runs` |

Each showcase directory has its own `README.md` with the chat-room and
conversation identifiers, the BO-MCP campaign identifiers, and a description of
its subdirectories.

## Layout convention

Directory names from the original campaign archive are preserved verbatim,
because the manuscript SI cites campaign artifacts by these paths:

- `gallery_guest_<room-id>-chat/` — exported agent conversation
  (`model_messages.json`, a pydantic-ai message history).
- `gallery_guest_<room-id>-workspace/` — the agent's working directory: campaign
  packages it authored, run logs, BO-MCP exports, evaluation records, generated
  structures, plots.
- `gallery_guest_<room-id>/` — used where chat and workspace were archived as a
  single directory.
- `logfire_trace_exports/` — per-conversation Logfire message-history exports
  (main agent and subagents), where they were captured.

Room identifiers are millisecond epoch timestamps of room creation, so they sort
chronologically.

## Sanitization and integrity

The copy was scanned and redacted for credential-shaped values with
`scripts/sanitize_snapshot.py showcases`; counts are in
`SANITIZATION_REPORT.json` in this directory. The agent workspaces read BO-MCP
and model API keys from the environment, so scripts and runbooks refer to
variables such as `BO_MCP_API_KEY` by name; any value-shaped match is replaced
with `[REDACTED]`.

`MANIFEST.sha256` at the repository root covers this tree as well; regenerate it
with `python scripts/build_manifest.py`.

## Why no Git LFS here

`snapshots/**` uses LFS because its conversation and PostgreSQL dumps run to
tens of megabytes each. This tree does not: no file reaches 5 MB, and most of it
(CSV, JSONL, logs, Python) is diffable text that packs well in plain Git. The
LFS filters in `.gitattributes` are scoped to `snapshots/**` and therefore do
not match anything here.
