# La Agente Óptima — research artifacts

This repository collects the raw data underlying *La Agente Óptima: Towards
Agentic Self-Driving Laboratories* — the run evidence, audit metadata, plotting
code, and figures for the framework comparison, plus the raw run evidence for
the showcase campaigns reported in the main text and SI.

**La Agente Óptima** (Óptima) is the agentic framework evaluated in the paper: a
coordinating agent plus a Bayesian optimization (BO) specialist subagent that
authors and supervises BO campaigns, keeping LLM reasoning separate from the
programmatically executed optimization loop.

**BO-MCP** is the BO backend service Óptima optimizes through. It holds
campaign configuration, accumulated observations, and the per-campaign action
ledger in its database, and exposes them over MCP and a REST API. Repo:
**[AccelerationConsortium/bo-mcp](https://github.com/AccelerationConsortium/bo-mcp)**.

## Repository layout

- `snapshots/` — the **framework comparison** (SI, *Framework comparison*): raw
  evaluation cells, controller metadata, and the comparison report. Described
  below.
- `showcases/` — the **showcase campaigns** reported in the paper and SI: OSL
  combinatorial discovery, four finite-space computational campaigns, the RAISE
  closed loop, and the RoboChem-Flex flow-photochemistry campaign. See
  `showcases/README.md`.

## Experimental platforms

Two showcases ran Óptima against external self-driving laboratories:

- **RAISE** (Robotic Autonomous Imaging Surface Evaluator) — closed-loop
  contact-angle formulation discovery.
  Repo: [Frank-Gu-Lab/RAISE](https://github.com/Frank-Gu-Lab/RAISE).
  Paper: Nazeri *et al.*, *Digital Discovery* **5**, 2254–2270 (2026),
  [10.1039/D5DD00531K](https://doi.org/10.1039/D5DD00531K).
- **RoboChem-Flex** — modular, low-cost flow-chemistry platform used for the
  multi-objective flow-photochemistry campaign.
  Repo: [Noel-Research-Group/Robochem_Flex](https://github.com/Noel-Research-Group/Robochem_Flex).
  Paper: Pilon *et al.*, *Nature Synthesis* (2026),
  [10.1038/s44160-026-01053-0](https://doi.org/10.1038/s44160-026-01053-0).

## Framework-comparison snapshot contents

The comparison evaluates the proposed Óptima architecture
(`Specialist-script`) against the `Main-script`, `Tool-loop`, and `Local-BO`
ablations, and additionally varies the LLM assigned to the BO specialist, over
the Ackley 6D and Shields arylation benchmarks.

The current snapshot includes the corrected BayBE duplicate-resuggestion
replacements and the latest comparison report. Results remain subject to
manuscript review; prior snapshot states are preserved in Git history.

`snapshots/2026-08-08-current/` contains:

- `raw/`: all 66 canonical cells used by the current report, organized by arm,
  case, and repeat. Cell directories retain conversations, metrics, logs,
  scripts, result artifacts, and request ledgers where available.
- `source_controls/`: controller metadata and PostgreSQL snapshots used to
  reconstruct campaign-level evidence.
- `report/`: the full comparison report, figures, pricing rules, cost and budget
  audits, selection audit, plotting scripts, and integrity manifest.

The published copies have been scanned and sanitized for API-key-shaped values.
Original research-server evidence was not modified. Sanitization counts are in
`snapshots/2026-08-07-preliminary/SANITIZATION_REPORT.json`.

`MANIFEST.sha256` is the portable integrity manifest for this repository. The
manifest under `report/control/` is retained from the research server for source
provenance and contains its original absolute paths.

## Rebuild the figures

Create an environment with Python 3.12 and install the plotting requirements:

```bash
python -m pip install -r requirements.txt
python scripts/rebuild_figures.py
```

The script reads the frozen `REPORT_DATA.json` and writes the figures back to
the snapshot's `report/figures/` directory.

## Status definitions

- Budget PASS: exactly 60 attempted objective evaluations in total across all
  campaigns owned by the run.
- Scientific PASS: the evaluation results are complete, unique, schema-valid,
  and use the expected backend.
- Architecture PASS: the intended main-agent/specialist ownership and required
  artifacts are present.

Campaign count is descriptive. One or multiple campaigns are allowed.
