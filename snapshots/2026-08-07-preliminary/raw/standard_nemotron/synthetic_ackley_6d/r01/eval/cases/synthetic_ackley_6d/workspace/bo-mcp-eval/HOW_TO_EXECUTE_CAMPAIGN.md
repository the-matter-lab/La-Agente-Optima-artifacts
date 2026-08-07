# How to Execute the Ackley 6D BO-MCP Campaign

## Overview

This campaign runs a Bayesian optimization over the **Ackley function in 6 normalized dimensions** using the **BO-MCP** (Bayesian Optimization Model Control Plane) service. The objective is to **maximize `surface_response`**, a normalized transformation of the classic Ackley function.

**Ownership marker:** Every campaign created by this script includes `akg-eval-fd1886f5b43b4509a3ee02d638497312` in its name. Only campaigns with this marker belong to this invocation.

---

## Prerequisites

### Environment Variables (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `BO_MCP_API_URL` | Base URL of the BO-MCP REST API | `http://api:8000` |
| `BO_MCP_API_KEY` | API key for authentication | `sk-...` |

### Environment Variables (Optional, for Logfire/GraphChat context)

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPHCHAT_AGENT_WS_URL` / `VITE_WS_URL` | `ws://graphchat:3000` | WebSocket URL for monitoring |
| `GRAPHCHAT_ROOM` | `room` | Room identifier |
| `SPARQL_ENDPOINT` | `http://blazegraph:8080/blazegraph/namespace/kb/sparql` | SPARQL endpoint |

### Python Dependencies

The script runs in the project's `uv` environment. The `grafico` package must be installed in editable mode **with `--no-build-isolation`** to avoid a timestamp error on this filesystem (`error: Cannot update time stamp of directory 'grafico.egg-info'`).

**One-time setup (run once per container/workspace):**
```bash
cd /path/to/workspace/bo-mcp-eval
uv pip install -e . --no-build-isolation
```

After this, run the campaign directly with `python` (not `uv run`):
```bash
python run_ackley_opt.py
```

The script runs in the project's `uv` environment. Ensure you're in the workspace directory:

```bash
cd /path/to/workspace/bo-mcp-eval
uv sync  # if needed
```

---

## Execution

### First Run (New Campaign)

```bash
```bash
export BO_MCP_API_URL=http://api:8000
export BO_MCP_API_KEY=[REDACTED]
python run_ackley_opt.py
```

### Resume Existing Campaign
```bash
python run_ackley_opt.py --campaign-id <CAMPAIGN_ID>
```
export BO_MCP_API_KEY=[REDACTED]
uv run python run_ackley_opt.py
```

### Resume Existing Campaign

```bash
uv run python run_ackley_opt.py --campaign-id <CAMPAIGN_ID>
```

### Common Options

| Option | Default | Description |
|--------|---------|-------------|
| `--random-seed` | 42 | RNG seed for reproducible initialization |
| `--initial-design-size` | 10 | Number of Sobol initial design points |
| `--batch-size` | 1 | Suggestions per generation call |
| `--max-observations` | 60 | **Total attempted evaluation budget** (including duplicates/failures) |
| `--backend` | `auto` | BO backend: `auto`, `botorch`, or `baybe` |
| `--acquisition-method` | `auto` | Acquisition function (e.g., `noisy_ei`, `upper_confidence_bound`) |
| `--artifact-dir` | `artifacts` | Output directory for artifacts |
| `--heartbeat-s` | 1800 | Heartbeat log interval (seconds) |
| `--stop-file` | `STOP` | Path to stop file |

---

## Stop / Resume Semantics

### Graceful Pause (Stop File)

Create the stop file to request a graceful pause at the **next loop iteration boundary**:

```bash
touch STOP
```

The script checks for this file at the top of each iteration (before generating suggestions). When detected:

1. Prints `[EVENT] Stop file detected; requesting pause`
2. Deletes the stop file (so resume isn't blocked by a stale marker)
3. Calls `lifecycle(campaign_id, action="pause")` on the server
4. Exits cleanly

### Resume After Pause

Re-run the same command with `--campaign-id`:

```bash
uv run python run_ackley_opt.py --campaign-id <CAMPAIGN_ID>
```

The script will:
- Verify the campaign has the ownership marker
- Load existing results from the server (populating the deduplication cache)
- Continue the optimization loop from the server's current state

### Resume After Completion (Reopen)

If the campaign shows `status: completed` (e.g., budget exhausted), use the same resume command. The script will call `lifecycle(action="reopen")` internally via the server's next-action logic.

**Never** recreate a campaign by replaying results as seeds — always resume or reopen.

---

## Console Output Tags

The script emits **tagged, unbuffered lines** for the main-agent monitor:

| Tag | Purpose | Example |
|-----|---------|---------|
| `[EVENT]` | State changes, lifecycle | `[EVENT] Created campaign abc123` |
| `[ALERT]` | Failures, warnings, stop conditions | `[ALERT] Evaluation failed: ...` |
| `[RESULT]` | Per-evaluation objective values | `[RESULT] Eval 5: surface=0.987654, raw=22.012345, ...` |
| `[HEARTBEAT]` | Liveness (every `--heartbeat-s` seconds) | `[HEARTBEAT] Campaign abc123 running, 23 evaluations so far` |

**All other output** (tracebacks, verbose logs) goes to the logfire trace / run log on disk.

---

## Output Artifacts

All artifacts are written to `--artifact-dir` (default: `./artifacts/`):

| File | Format | Description |
|------|--------|-------------|
| `results.jsonl` | JSON Lines | **Primary artifact** — one row per attempted evaluation with: `evaluation_index`, `parameter_values`, `objective_values`, `status`, `failure_reason`, `raw_response` |
| `results.csv` | CSV | Human-readable table with coordinates, responses, status |
| `server_export.csv` | CSV | Full campaign export from BO-MCP server |

### `results.jsonl` Schema (one line per evaluation)

```json
{
  "evaluation_index": 0,
  "parameter_values": {"x_1": 0.5, "x_2": 0.3, "x_3": 0.7, "x_4": 0.1, "x_5": 0.9, "x_6": 0.4},
  "objective_values": {"surface_response": 0.852341},
  "status": "success",
  "failure_reason": null,
  "raw_response": 19.054321
}
```

**Status values:** `success`, `failed`, `duplicate`

**Deduplication:** The script prevents re-evaluation of identical coordinates (tracks in-memory cache + loads from server on resume).

---

## Campaign ID

The campaign ID is emitted in two ways:

1. **Console (final line):** `BO_MCP_CAMPAIGN_ID=<campaign_id>`
2. **Logfire traces:** Available in the `campaign_id` attribute on all spans

When resuming, pass this ID via `--campaign-id`.

---

## Search Space & Objective (Reference)

### Parameters (6 continuous, normalized [0,1])

- `x_1`, `x_2`, `x_3`, `x_4`, `x_5`, `x_6` — all in `[0.0, 1.0]`

### Mapping to Ackley Coordinates

```
z_i = -40 + 80 * x_i    for i = 1..6
```

### Classic Ackley Function

```
classic = -20*exp(-0.2*sqrt(sum(z_i^2)/6)) - exp(sum(cos(2*pi*z_i))/6) + 20 + e
```

Global minimum: `classic = -22.350402387287602` at `z = (0,0,0,0,0,0)` → `x = (0.5, 0.5, 0.5, 0.5, 0.5, 0.5)`

### Objective Transformation

```
raw_response = -classic
surface_response = (raw_response - (-22.350402387287602)) / (0.0 - (-22.350402387287602))
                 = (raw_response + 22.350402387287602) / 22.350402387287602
```

- **Maximize** `surface_response` (range `[0, 1]`, optimum = 1.0 at `x = (0.5, ..., 0.5)`)
- Deterministic, no noise
- No additional negation or rescaling

---

## Expected Runtime

- **60 evaluations** × fast Python function ≈ seconds to minutes total
- BO suggestion generation (BO-MCP server) dominates: ~10-60s per batch depending on backend
- Total wall time: typically **5-15 minutes** for full budget

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| `BO_MCP_API_URL` / `BO_MCP_API_KEY` not set | Export both before running |
| Campaign creation rejected | Check intake validation errors in `[ALERT]` output; verify backend supports acquisition method |
| Duplicate suggestions submitted | Script handles via `status=duplicate` + `update_suggestion_status=rejected`; check `[ALERT]` lines. Duplicates count toward the `--max-observations` budget. |
| Server timeout on `generate_suggestions` | Increase `--heartbeat-s` or check server logs; generation can take minutes for complex spaces |
| Stop file ignored | Stop file checked at **iteration boundary only** (before generation), not mid-evaluation |
| Budget exceeded unexpectedly | Budget is tracked locally as **attempted evaluations** (including duplicates/failures); `--max-observations` limits total artifact rows, not just server `n_results` |
| `uv run` fails with `Cannot update time stamp of directory 'grafico.egg-info'` | Run `uv pip install -e . --no-build-isolation` once, then use `python run_ackley_opt.py` directly |
| Campaign creation rejected | Check intake validation errors in `[ALERT]` output; verify backend supports acquisition method |
| Duplicate suggestions submitted | Script handles via `status=duplicate` + `update_suggestion_status=rejected`; check `[ALERT]` lines. Duplicates count toward the `--max-observations` budget. |
| Server timeout on `generate_suggestions` | Increase `--heartbeat-s` or check server logs; generation can take minutes for complex spaces |
| Stop file ignored | Stop file checked at **iteration boundary only** (before generation), not mid-evaluation |
| Budget exceeded unexpectedly | Budget is tracked locally as **attempted evaluations** (including duplicates/failures); `--max-observations` limits total artifact rows, not just server `n_results` |
| Server timeout on `generate_suggestions` | Increase `--heartbeat-s` or check server logs; generation can take minutes for complex spaces |
| Stop file ignored | Stop file checked at **iteration boundary only** (before generation), not mid-evaluation |

---

## File Layout

```
bo-mcp-eval/
├── run_ackley_opt.py          # Entry point (CLI)
├── ackley_opt/                # Campaign package
│   ├── __init__.py
│   ├── search_space.py        # Parameter/objective definitions, intake builder
│   ├── evaluate.py            # Ackley function + candidate evaluation
│   ├── report.py              # Summary, tables, artifact writers
│   └── campaign.py            # Orchestration loop (BoMcpClient)
├── artifacts/                 # Output directory (created at runtime)
│   ├── results.jsonl
│   ├── results.csv
│   └── server_export.csv
├── STOP                       # Stop file (create to pause)
└── campaign_manifest.json     # Package manifest
```

---

## Validation Checklist

After a run completes, verify:

- [ ] `BO_MCP_CAMPAIGN_ID=<id>` printed at end
- [ ] `artifacts/results.jsonl` has 60 lines (one per attempted evaluation)
- [ ] No duplicate coordinates in `results.jsonl`
- [ ] Best `surface_response` ≈ 1.0 (theoretical max at `x_i = 0.5`)
- [ ] Summary table printed with `[RESULT]` tags for each evaluation
- [ ] Campaign shows `status: paused` (or `completed`) on server