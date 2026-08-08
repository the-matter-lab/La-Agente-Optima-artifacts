# Direct Arylation Yield Campaign — Execution Guide

BO-MCP campaign (BayBE backend) that maximizes reaction `yield` (percent) over the fixed,
fully crossed 1,728-condition direct arylation grid, measured only through the oracle service.

Campaign name / ownership marker (present in every campaign created here):
`direct-arylation-yield-akg-eval-1c094af49d534fef9861377f221f0f69`

## Execution command (recommended)

```bash
cd <this workspace>
uv run --project /app python -u run_direct_arylation_bo.py \
  --campaign-id e310a3b3-a78d-4a67-bfd5-489e87b9fd87 --max-attempts 56
```

The smoke test already ran **4 attempted evaluations (4 successful)** on that campaign, so
`--max-attempts 56` completes the required **60 attempted evaluations total**. The campaign is
currently `paused`; the script resumes it automatically.

Starting a brand-new campaign instead (drops the 4 existing measurements, still marker-named):

```bash
uv run --project /app python -u run_direct_arylation_bo.py --max-attempts 60
```

Re-running the exact same command with `--campaign-id` after a kill/pause resumes where the
server left off — no local loop state is kept.

## Environment requirements

| Variable | Purpose |
| --- | --- |
| `BO_MCP_API_URL`, `BO_MCP_API_KEY` | BO-MCP REST API (via `BoMcpClient.from_env()`; fails fast if missing) |
| `DIRECT_ARYLATION_API_URL` | Oracle base URL; the script POSTs `${DIRECT_ARYLATION_API_URL}/v1/evaluate` |
| `LOGFIRE_TOKEN` (optional) | Logfire request instrumentation |

All three BO/oracle variables are already set in this container.

## Campaign design

- Backend: `baybe`, pinned (`backend: "baybe"`).
- Parameters (exact, lowercase): `base` (4 categorical), `ligand` (12 categorical),
  `solvent` (4 categorical, `Butyornitrile` spelling preserved), `concentration`
  (discrete 0.057 / 0.1 / 0.153), `temperature_c` (discrete 90 / 105 / 120).
- Encoding: one-hot (`parameter_options.baybe.encoding = "OHE"`) for the three categoricals —
  the labels carry no usable ordinal structure; numeric parameters stay on their measured grid.
- Objective: single, `yield`, `direction: maximize`, unit `percent`.
- Initialization: `initial_design_size = 8` space-filling points, then model-driven acquisition.
- Acquisition: `expected_improvement` (BayBE qLogEI), `random_seed = 42`.
- Schedule: `batch_size = 1` (sequential, one suggestion per BO iteration — best sample
  efficiency for a 60-evaluation budget). Override with `--batch-size N` if wall-clock matters.
- `max_iterations` / `max_observations` are intentionally left unset in the immutable intake;
  the 60-attempt budget is a CLI budget (`--max-attempts`), plus a server-side result cap
  (`--max-successes`, default 60).

## Loop behavior

Per iteration: check the stop file → `next_action(campaign_id)` (the server owns the
continue/stop decision) → `generate_suggestions` → snap the suggestion onto the exact grid →
POST to the oracle → record the attempt → submit successful results (a duplicate rejection is
retried once with `force=True` under a fresh idempotency key; BayBE may deliberately replicate).

- A non-2xx oracle response or transport error counts as a **failed attempted evaluation**: it is
  recorded with `status: "failed"` plus `error`/`http_status`, the suggestion is marked
  `rejected` on the server, and the loop continues **within the same attempt budget**. No penalty
  value is ever submitted for a failure.
- The loop stops when the per-invocation attempt budget is spent, when the stop file appears,
  when the server's `n_results` reaches `--max-successes`, or when `next_action` returns anything
  other than `bo_generate_suggestions` (printed as `[ALERT]`). If a server-side stop arrives
  before 60 attempts, the run pauses early — review the `[ALERT]` line and decide whether to
  continue with a fresh invocation.
- At the end of an invocation the campaign is **paused** (never terminated) if it is still
  running, so the same command resumes it.

## Stdout tags (monitor-friendly)

| Tag | Meaning |
| --- | --- |
| `[EVENT]` | State changes: create/resume/pause, stop-file shutdown, final summary, artifact paths |
| `[ALERT]` | Oracle failures, empty generation, server-side stop conditions |
| `[RESULT]` | Full per-attempt analysis: attempt index, yield, running best, all five conditions |
| `[HEARTBEAT]` | Liveness (every `--heartbeat-s`, default 1800 s) |

Everything else (HTTP traces, detail) goes to the run log: `logs/run_<timestamp>.log`.

## Stop / resume

- Stop file: `STOP` in this workspace (override with `--stop-file PATH`).
  `touch STOP` — it is checked at the top of each iteration *before* a suggestion is generated,
  never between evaluation and submission. When found, the script prints `[EVENT]`, deletes the
  marker (so the resume command is not blocked by a stale file), pauses the campaign, writes the
  artifacts, and exits normally.
- Resume: re-run the same command with `--campaign-id <id>`; the script resumes a `paused`
  campaign and reopens a `completed` one.

## Outputs

| Path | Content |
| --- | --- |
| `artifacts/attempts.jsonl` | Append-only, one JSON record per attempted evaluation (all invocations) |
| `artifacts/attempts.json` | Standardized JSON array of every attempt recorded in this workspace |
| `artifacts/final_report_<timestamp>.json` | Per-invocation final report (see below) |
| `logs/run_<timestamp>.log` | Verbose run log |
| `campaign_manifest.json` | Module paths, entrypoint, artifact dir, smoke-test campaign id |

Attempt record shape (success):

```json
{
  "parameter_values": {"base": "Cesium pivalate", "ligand": "XPhos", "solvent": "Butyornitrile",
                       "concentration": 0.153, "temperature_c": 120},
  "objective_values": {"yield": 78.44},
  "status": "success", "http_status": 200, "duration_s": 0.8,
  "suggestion_id": "...", "attempt": 1, "attempt_budget": 56, "iteration": 2,
  "successes": 1, "best_yield": 78.44
}
```

Failed attempt: same `parameter_values`, `status: "failed"`, `error`, optional `http_status`,
and no `objective_values`.

`final_report_<timestamp>.json` contains `campaign_id`, `objective`, `attempted_evaluations`,
`successful_evaluations`, `failed_evaluations`, `best_yield_percent`, `best_conditions`, and
`evaluated_candidates` (every attempt with its status and objective value). The same numbers are
echoed to stdout as `[EVENT] summary: ...` and `[EVENT] best yield=...`.

## Validation performed before handoff

- `python -m py_compile` on the entrypoint and all package modules.
- `validate_intake` accepted the BayBE intake (encoding options, discrete grids, acquisition).
- Smoke test: create + 1 iteration; then resume + 2 iterations, then resume + 1 iteration (initial-design and BO phases);
  stop-file path (marker consumed, clean shutdown); failure-record shape for HTTP 404 and a DNS
  error. Artifacts, tags, and pause/resume all verified. The full campaign was **not** run.

## Notes before execution

- The oracle is a lookup service and responds in milliseconds, so 56 sequential iterations are
  dominated by BayBE suggestion generation (~1 s each early on, growing slowly).
- `--poll-s` (default 180) is only the retry wait when a generation call returns no suggestions.
- Never edit `artifacts/attempts.jsonl`: it is provenance, and the loop never reads it for
  decisions (only for the final report/snapshot).
