# 6D Ackley synthetic BO campaign — how to execute

Controlled synthetic benchmark. **No chemistry/experimental evaluator is called**
(no PySCF, CREST, MOF, RAISE, RoboFlex). The objective is a deterministic Python
function inside the package.

Cache-buster nonce: `f42213a0-34a7-4c2a-bbef-8b4700e0fb91`
Campaign marker (required in every created campaign name): `akg-eval-7f1274a8431e4c5d94a3b24374899d9e`

## Files

| Path | Purpose |
| --- | --- |
| `run_ackley6d_bench.py` | CLI entrypoint (Logfire config + arg wiring only) |
| `ackley6d_bench/space.py` | search space: `x_1..x_6` continuous in `[0, 1]` |
| `ackley6d_bench/objective.py` | deterministic objective (Ackley → `surface_response`) |
| `ackley6d_bench/intake.py` | BO-MCP campaign intake (BayBE backend) |
| `ackley6d_bench/harness.py` | campaign-agnostic evaluation harness (failure capture) |
| `ackley6d_bench/reporting.py` | JSONL artifact rows + tagged stdout reporting |
| `ackley6d_bench/campaign.py` | BO-MCP loop orchestration via `BoMcpClient` |
| `campaign_manifest.json` | module paths, entrypoint, latest artifact dir |

## Campaign configuration

- Backend: **BayBE** (pinned, `backend="baybe"`).
- Objective: name `surface_response`, direction `maximize`, unit `normalized_unitless`.
- Search space: six continuous normalized dimensions `x_1 … x_6 ∈ [0.0, 1.0]`.
- Strategy (chosen for this run): `random_seed=20481`, `initial_design_size=12`
  space-filling warmup, then model-driven `expected_improvement`, batch size 4
  throughout (60 = 15 batches of 4).
- `max_iterations` is intentionally **unset** in the intake so the campaign can be
  reopened/resumed later; the 60-evaluation budget is a CLI budget.

## Objective (deterministic, no noise)

For each candidate: `z_i = -40 + 80 * x_i`, `d = 6`

```
classic          = -20*exp(-0.2*sqrt(sum(z_i^2)/d)) - exp(sum(cos(2*pi*z_i))/d) + 20 + e
raw_response     = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
```

`surface_response = 1.0` at the optimum (`x_i = 0.5` for all i).

## Environment

`BO_MCP_API_URL` and `BO_MCP_API_KEY` must be set (they are, in this container).
Run from this workspace directory with the repo's uv environment.

## Command (recommended: continue the already-created campaign)

A campaign with the required marker already exists and holds 8 stored evaluations
from the bounded smoke test:

- campaign id: `f36d19dc-5f95-4b71-82f7-c82867261e06`
- campaign name: `ackley6d-synthetic-akg-eval-7f1274a8431e4c5d94a3b24374899d9e-20260807T055051Z`

```bash
uv run --project /app python -u run_ackley6d_bench.py \
  --campaign-id f36d19dc-5f95-4b71-82f7-c82867261e06 \
  --max-evaluations 60 \
  --poll-s 180 --heartbeat-s 1800
```

To start a brand-new campaign instead (also marker-compliant), omit `--campaign-id`.
Re-running the exact same command after a kill/stop resumes from server state.

### CLI options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--campaign-id` | none | resume (paused) / reopen (completed) an existing campaign |
| `--max-evaluations` | `60` | campaign-wide attempted-evaluation budget; already-stored results count toward it |
| `--artifacts-dir` | `artifacts/<UTC timestamp>` | where `results.jsonl` and `run.log` are written |
| `--stop-file` | `STOP` (cwd) | interrupt marker, see below |
| `--poll-s` | `180` | wait before retrying when suggestion generation returns nothing |
| `--heartbeat-s` | `1800` | liveness print interval |

## Behavior

1. Create (or resume/reopen) the campaign; the marker is verified on resume.
2. Loop, per iteration: check stop file → `next_action` → `generate_suggestions`
   (batch 4, trimmed so the budget is never exceeded) → deterministic evaluation →
   submit results. Duplicate coordinates are never evaluated twice: a repeated
   point is rejected via `update_suggestion_status` and the loop continues.
3. Loop stops when the budget is met, the stop file appears, or the server's
   `next_action` no longer recommends generating suggestions.
4. On shutdown the campaign is **paused** (never terminated) and a full summary +
   candidate table is printed.

## Stop file

`STOP` in the current working directory (override with `--stop-file`). It is checked
at the top of each iteration *before* a suggestion is generated — never between
evaluation and submission. When found the run prints `[EVENT] stop file found …`,
deletes the file (so the resume command is not blocked by a stale marker), pauses
the campaign, prints the report, and exits. Resume with the same command plus
`--campaign-id`.

## Stdout tags (monitor-friendly)

| Tag | Emitted for |
| --- | --- |
| `[EVENT]` | campaign create/resume/pause, budget, submissions, summary, artifacts, campaign id |
| `[ALERT]` | failed evaluations, duplicate suggestions, server-side stop conditions |
| `[RESULT]` | one line per evaluated candidate: coordinates, `raw_response`, `surface_response`, status |
| `[HEARTBEAT]` | liveness: `<attempted>/<budget> evaluations attempted` |

Everything else (HTTP traces, `next_action` payloads) goes to `<artifacts-dir>/run.log`
and Logfire. Logfire request instrumentation is enabled in the entrypoint header.

## Outputs

- `<artifacts-dir>/results.jsonl` — one JSON row per evaluated candidate with
  `evaluation_index`, `parameter_values {x_1..x_6}`, `objective_values {surface_response}`,
  `raw_response`, `status`, `failure_reason`, `suggestion_id`.
- `<artifacts-dir>/run.log` — full timestamped run log.
- Final stdout report: best coordinates, best `raw_response`, best `surface_response`
  (`normalized_unitless`), successful/attempted counts, and a table of all evaluated
  candidates with objective values/status.
- Last two lines contain the campaign id:
  `[EVENT] final BO_MCP_CAMPAIGN_ID=<id>` and the bare `BO_MCP_CAMPAIGN_ID=<id>`
  line required by the user answer.

## Validation already performed

- One-batch smoke run (4 evaluations) creating the marker-compliant campaign.
- Resume run (`--campaign-id`, 4 more evaluations, total 8) — resume + budget
  accounting from server state verified.
- Stop-file run — marker detected, deleted, clean paused shutdown verified.
- No full 60-evaluation run has been executed.
