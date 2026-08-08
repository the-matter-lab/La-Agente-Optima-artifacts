# Ackley-6D BayBE BO-MCP Campaign — Execution Guide

Cache-buster nonce: 20c0e1a3-857c-440c-9206-992c37c2f31f

This is a controlled **synthetic benchmark**. The objective is a pure,
deterministic 6D Ackley function evaluated in Python — the script never
calls PySCF, CREST, MOF/PORMAKE, RAISE, RoboFlex, or any other chemistry
or experimental evaluator. All optimization is delegated to BO-MCP
(BayBE backend); there is no local-results-only branch.

## Exact execution command

```bash
python run_ackley6d_baybe.py
```

To resume/continue a specific existing campaign (e.g. after an interrupt,
or to continue the smoke-tested campaign recorded in `campaign_manifest.json`):

```bash
python run_ackley6d_baybe.py --campaign-id <CAMPAIGN_ID>
```

Optional flags:
- `--poll-s` (default `180`, keep within 120–300): accepted for monitoring
  contract parity. This campaign's loop is synchronous pure-math evaluation
  (no external async job to poll), so it has no effect on pacing; it is
  logged once at start via `[EVENT]`.
- `--heartbeat-s` (default `1800`): liveness heartbeat interval.
- `--stop-file` (default `STOP`): see Stop/Resume behavior below.

## Expected environment / setup

- Run from this workspace directory (`uv run python run_ackley6d_baybe.py`
  or plain `python run_ackley6d_baybe.py` inside the project's `uv` env).
- Requires `BO_MCP_API_URL` and `BO_MCP_API_KEY` in the environment
  (`BoMcpClient.from_env()` fails fast if either is missing).
- No PySCF/CREST/GPU/chemistry setup is needed for this campaign.

## Expected campaign behavior

- **Backend**: BayBE, pinned explicitly (`backend: "baybe"` in the intake).
- **Search space**: `x_1`..`x_6`, each continuous on `[0.0, 1.0]`.
- **Objective**: `surface_response` (maximize, unit `normalized_unitless`),
  computed as:
  - `z_i = -40 + 80 * x_i`
  - `classic = -20*exp(-0.2*sqrt(sum(z_i^2)/6)) - exp(sum(cos(2*pi*z_i))/6) + 20 + e`
  - `raw_response = -classic`
  - `surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))`
  - Deterministic — no noise, no other rescaling/negation.
- **Seed / init / batching / acquisition** (chosen fresh for this campaign,
  see `ackley6d_baybe/intake.py` for the authoritative values and rationale):
  `random_seed=20240917`, `initial_design_size=12` (Sobol/random warmup),
  `batch_size=6`, `acquisition_method=upper_confidence_bound` (`beta=2.0`).
- **Budget**: exactly **60 attempted objective evaluations total** for the
  campaign, enforced by the script (not fossilized into the immutable
  intake as `max_iterations`). Attempted = successful (submitted to
  BO-MCP) + failed (recorded locally, suggestion rejected, not submitted
  since BO-MCP requires finite objective values). The script never submits
  the same point twice — each round it checks already-attempted points
  (from server results + a local failure log) before evaluating a new
  suggestion, and rejects/skips exact duplicates without spending budget.
- Each invocation re-derives progress from the BO-MCP server
  (`next_action`, `get_results`) rather than any local counter, per the
  BO-MCP client's loop-state policy. Only exception: a local
  `artifacts/<campaign_id>/failed_evaluations.jsonl` append-only file,
  which is the sole record of failed (never-submitted) attempts — BO-MCP
  has no concept of a failed external evaluation.

## Outputs / artifacts

All written under `artifacts/<campaign_id>/` (workspace-relative):
- `results.csv` — one row per **evaluated** candidate (built fresh at the
  end of every invocation from BO-MCP's persisted results + the local
  failure log), with columns:
  `evaluation_index, x_1..x_6, surface_response, raw_response, status,
  failure_reason, suggestion_id`.
- `failed_evaluations.jsonl` — append-only provenance of failed attempts
  (only written if a failure occurs; absent otherwise).

Final report is also printed to stdout at the end of every invocation (see
tags below), and the campaign's authoritative result rows always remain
queryable directly from BO-MCP (`get_results` / `export_campaign`).

## Monitoring tags

- `[EVENT]` — state changes: campaign created/resumed/reopened/paused,
  budget reached, server stop signal, stop-file detected.
- `[ALERT]` — failures, rejected suggestions/results, duplicate skips,
  missing ownership marker (hard-stop).
- `[RESULT]` — full per-candidate outcome as each evaluation completes,
  and the final campaign report block (best coordinates, best
  `raw_response`, best `surface_response`, attempted/successful counts,
  CSV path), ending with a bare `BO_MCP_CAMPAIGN_ID=<campaign_id>` line.
- `[HEARTBEAT]` — liveness, emitted at least every `--heartbeat-s`.

Everything else (HTTP call traces via Logfire, etc.) goes to normal
stdout/Logfire, not gated behind these tags.

## Stop / resume behavior

- The loop checks `--stop-file` (default `STOP` in the current working
  directory) **at the top of each iteration, before generating new
  suggestions** — never between evaluating and submitting a batch, so an
  already-evaluated batch is always submitted before any pause.
- On detecting the stop file: prints `[EVENT]`, deletes the file (so a
  later resume isn't blocked by a stale marker), pauses the campaign
  (only if it is currently `running`), then exits through the normal
  final-report path.
- **Resume**: re-run with `--campaign-id <id>`. A `paused` campaign is
  resumed; a `completed` campaign (e.g. budget reached or BO-MCP declared
  convergence) is reopened. Either way the script re-derives its position
  from the server (existing results + local failure log) and continues
  only up to the fixed 60-evaluation total.

## How the final report artifact is produced

At the end of every invocation (budget reached, server stop signal, or
stop-file requested), the script:
1. Fetches the campaign (re-checks the ownership marker) and its full
   result set via `get_results`.
2. Loads the local failure log (if any).
3. Recomputes `raw_response` for each successful row directly from its
   stored `x_1..x_6` (BO-MCP's result schema stores only
   `objective_values`, not arbitrary metadata) using the same
   deterministic objective function — safe because the function is pure.
4. Writes/overwrites `artifacts/<campaign_id>/results.csv` with one row
   per attempted evaluation (success or failure).
5. Prints the `[RESULT]` summary block, including
   `BO_MCP_CAMPAIGN_ID=<campaign_id>` as the final bare line. **The parent
   agent's final answer to the user must include exactly this one line.**

## Ownership marker enforcement

- Marker: `akg-eval-01a2bebdff8c40379a2fd4b6ab495231` (see
  `ackley6d_baybe/intake.py::OWNERSHIP_MARKER`).
- Every campaign this script creates has it embedded in `CAMPAIGN_NAME`
  (`ackley6d-baybe-surface-response-<marker>`), asserted at intake-build
  time and again right after creation.
- On `--campaign-id` resume, and again at final reporting, the script
  fetches the campaign's `name` from BO-MCP and calls `_check_marker`:
  if the marker is missing, it prints `[ALERT]` and exits with a
  non-zero status **without** resuming, generating suggestions,
  submitting results, or reporting for that campaign.

## Notes for the parent agent

- A campaign already exists from authoring-time validation: see
  `campaign_manifest.json` → `smoke_test_campaign_id`
  (`84ceec99-fabc-408c-a7fa-3509f9552896`), created with the correct
  marker-bearing name and left **paused** with 4/60 successful
  evaluations already submitted (verified end-to-end: create → generate
  → evaluate → submit → budget/stop check → pause → report). You may
  continue it with `--campaign-id 84ceec99-fabc-408c-a7fa-3509f9552896`
  to reach the full 60, or start fresh by omitting `--campaign-id`
  (a brand-new campaign will be created, also with the required marker).
- `smoke_test_ackley6d_baybe.py` in this directory is an ephemeral
  authoring-time helper (temporarily monkeypatches the budget to 4 for a
  fast check) — it is not part of the deliverable and is not needed for
  normal execution; it can be ignored or deleted.
- The full 60-evaluation run is expected to complete in well under a
  minute of wall-clock BO-MCP calls (10 batches of 6, deterministic
  pure-Python evaluation) — no long external compute is involved.
