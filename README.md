# BO-MCP benchmark artifacts

This private repository collects the raw run evidence, audit metadata, plotting
code, and figures for the BO-MCP framework comparison.

The current snapshot includes the corrected BayBE duplicate-resuggestion
replacements and the latest comparison report. Results remain subject to
manuscript review; prior snapshot states are preserved in Git history.

## Snapshot contents

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
