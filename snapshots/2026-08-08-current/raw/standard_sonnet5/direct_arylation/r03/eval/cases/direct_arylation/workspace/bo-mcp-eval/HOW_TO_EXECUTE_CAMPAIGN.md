# Direct Arylation Yield — BO-MCP Campaign (BayBE backend)

Optimizes measured `yield` (percent, maximize) over the fixed 1,728-candidate
direct-arylation search space (`base` x `ligand` x `solvent` x `concentration`
x `temperature_c`) using BO-MCP's BayBE backend. Every candidate is scored by
the external oracle at `DIRECT_ARYLATION_API_URL`; no local BO, no CSV/table
lookup, no enumeration of the space.

- Ownership marker (present in the campaign name of every campaign this
  package creates): `akg-eval-9209d1682dba47dfb5f5735d25356061`
- Cache-buster nonce (informational only): `4b764ac7-d36a-4203-89a4-800a2274f65c`
- Attempt budget: **exactly 60** oracle evaluations total (success + failure
  both consume budget). Never exceed it.

## Required environment

- `BO_MCP_API_URL`, `BO_MCP_API_KEY` — BO-MCP REST API.
- `DIRECT_ARYLATION_API_URL` — oracle base URL (script POSTs
  `${DIRECT_ARYLATION_API_URL}/v1/evaluate`).

All three are checked at startup; the script exits with `[ALERT]` + code 2 if
any is missing.

## A smoke-tested campaign already exists — resume it, do not create a new one

`campaign_manifest.json` records a real BO-MCP campaign already created and
exercised by this authoring session (`smoke_test.campaign_id`
`3447e24a-05e0-46d1-99ce-3698696de27d`, name
`direct-arylation-yield-baybe-akg-eval-9209d1682dba47dfb5f5735d25356061`,
backend `baybe`), currently **paused** with **3/60** attempts already
consumed (2 successful oracle evaluations + 1 induced connectivity-failure
test, both legitimate attempts against the budget). Continue this same
campaign so the total stays at exactly 60 attempts:

```bash
uv run python run_direct_arylation_baybe.py \
  --campaign-id 3447e24a-05e0-46d1-99ce-3698696de27d \
  --budget 60
```

If for any reason that campaign is unusable, only then create a fresh one by
omitting `--campaign-id` — the script will create a new campaign whose name
still carries the exact marker above.

## Command

```bash
uv run python run_direct_arylation_baybe.py [--campaign-id ID] [--budget 60] \
    [--poll-s 180] [--heartbeat-s 1800] [--stop-file STOP] \
    [--artifact-dir direct_arylation_baybe_artifacts]
```

- `--budget` (default 60): total attempted oracle evaluations for this
  benchmark. The script derives how many attempts are *already* consumed
  from BO-MCP's own suggestion records (server truth: every non-`pending`
  suggestion is one used attempt), so re-running with `--campaign-id` never
  double-spends the budget, even across kills/restarts.
- `--poll-s` (120-300, default 180): timeout bound for a single
  `generate_suggestions` call.
- `--heartbeat-s` (default 1800): minimum interval between `[HEARTBEAT]`
  lines.
- `--stop-file` (default `STOP`): create this file in the working directory
  to request a graceful pause. It is checked only at the top of each loop
  iteration (before requesting/reusing a suggestion) — never between
  evaluating a candidate and submitting its result — so a stop request never
  strands an already-evaluated measurement. The file is deleted once
  consumed so a later resume isn't blocked by a stale marker.

## Resuming after a pause or kill

Re-run the exact same command with `--campaign-id <the printed id>` (see
`[EVENT] created campaign_id=...` / `[EVENT] BO_MCP_CAMPAIGN_ID=...` in the
output). The script resumes a paused campaign or reopens a completed one
automatically, then re-derives its position from BO-MCP (never from a local
file) and continues until the 60-attempt budget is reached or the server's
`next_action` says to stop.

## Stdout tags (what the monitor forwards)

- `[EVENT]` — campaign created/resumed/reopened/paused, stop-file detected,
  loop-ended, server-declared stop condition.
- `[ALERT]` — a failed oracle attempt, a rejected suggestion/result/creation,
  or any other stop condition worth surfacing.
- `[RESULT]` — one line per attempt (`status=success yield=NN.NNNpercent
  <conditions>` or a failure alert), plus the final `SUMMARY` line and one
  `candidate` line per evaluated suggestion (status + yield + parameters).
- `[HEARTBEAT]` — periodic liveness marker (at least every `--heartbeat-s`
  seconds) while attempts are still being made.

Everything else (HTTP call traces via Logfire, etc.) goes to the log file at
`<artifact-dir>/run.log`, not stdout.

## Artifacts (append-only provenance, never read back to steer the loop)

- `<artifact-dir>/results.jsonl` — one JSON line per attempt as it happens
  (`parameters`, `status`, `yield_percent`, `error`).
- `<artifact-dir>/summary.json` — final report written at the end of every
  invocation: `attempted`, `successful`, `failed`, `best_yield_percent`,
  `best_conditions`, and the full `candidates` list (each with
  `suggestion_id`, `parameters`, `status`, `yield_percent`).
- `<artifact-dir>/run.log` — verbose log (HTTP calls, logfire info).

The authoritative final report (`[RESULT] SUMMARY ...` and per-candidate
lines) is always rebuilt from BO-MCP's own suggestion + result rows at the
end of the run, so it is correct even if the JSONL file is lost.

## Reporting to the user

After the run (or after inspecting `summary.json` from the latest
`--artifact-dir`), report:
- Best conditions (`best_conditions`) and best measured yield
  (`best_yield_percent`).
- Counts: `attempted` (all oracle attempts) vs `successful`.
- All evaluated candidates with their `status` (`success`/`rejected`) and
  `yield_percent` (`null` for failures).
- The BO-MCP `campaign_id` (also printed as
  `[EVENT] BO_MCP_CAMPAIGN_ID=...`).

## Validation performed by the author (bo-pyscf-specialist)

- `python -m py_compile` on every package module and the entrypoint.
- Live smoke test against the real BO-MCP + oracle services: created the
  campaign (marker confirmed in the name), generated + evaluated 1
  suggestion, submitted its result, paused; resumed with a higher budget and
  confirmed server-truth attempt counting across the resume; verified the
  stop-file is detected/deleted at the top of an iteration; and verified
  failed-oracle-call handling (suggestion rejected, attempt still counted,
  no fabricated result submitted). The full 60-attempt budget was
  **not** spent — only 3 attempts (2 success, 1 induced failure) were used,
  and that same campaign is the one to resume for the full run (see above).
