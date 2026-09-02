# RoboChem-Flex agent campaign — run-level data for cost analysis

Exported 2026-08-05 from the campaign workspaces and platform run records in
`roboflex_exp-2026072/`. Four files:

| File | Content |
|---|---|
| `roboflex_runs_submitted.csv` | one row per run submitted to the platform (53 rows, `R0028`–`R0080`), parameters as executed, amounts consumed, outcome |
| `roboflex_reagents.csv` | reagent identities: CAS, molar mass, stock concentration prepared, stock mass weighed |
| `roboflex_campaign_summary.csv` | the same aggregated per campaign phase |
| `roboflex_runs_in_figure.csv` | **only the 23 experiments plotted in the paper figure**, with an `experiment_number` column (1-23) matching the figure labels |

## Which rows are the "agent campaign"

`phase` separates five blocks. **The reported campaign is the last three** (37 submissions,
`R0042`–`R0080`):

| phase | runs | note |
|---|---|---|
| `exploratory 23-24 Jul (discarded…)` | 14 | earlier session, different package and BO campaign; its measurements were never used. Include only if you want total material spent in the lab. |
| `aborted first attempt…` | 2 | `R0042` ran with the wrong NMR protocol (proton instead of ¹⁹F), `R0043` was a duplicate stopped in the queue |
| `yield + green score` | 23 | two-objective phase, `R0044`–`R0066` |
| `yield only` | 8 | single-objective refocus, `R0067`–`R0074` |
| `yield only, clean reseed` | 6 | reseeded campaign, `R0075`–`R0080` |

30 runs returned a valid yield. The 23 points in the paper figure are, in figure order:
`R0044`–`R0059`, `R0061`, `R0062`, `R0065`, `R0066`, `R0067` (experiments 1–21, carried into the
reseeded campaign as history) and `R0075`, `R0076` (experiments 22–23). Use
`roboflex_runs_in_figure.csv` for exactly that set.

Not plotted: `R0060`, `R0063`, `R0064` (analytical failures, never submitted to the optimizer),
`R0068`–`R0074` (discarded by the clean reseed), `R0077`–`R0079` (zero-yield analytical failures
excluded by the operator) and `R0080` (no result returned). `R0052`'s green score in the figure
file is recomputed from the campaign formula, because its original submission was lost while
BO-MCP was unavailable.

## Amounts: how they were computed

Every experiment is one 650 µL slug at 100 mM substrate, so the limiting reagent is fixed:

```
n_SM = 100 mM × 650 µL = 65 µmol per experiment   (column n_SM_umol)
```

Everything else is dosed in equivalents relative to that:

```
reagent_umol = equiv × 65 µmol
reagent_mg   = reagent_umol × MW / 1000
stock_uL     = 1000 × reagent_umol / real_conc_mM     (volume drawn from the prepared stock)
```

`real_conc_mM` and `MW` come from `roboflex_reagents.csv` (the measured stock concentrations, not
the targets). Solvent is the balance of the 650 µL slug.

**Two costing bases, pick deliberately:**

1. **Consumed** — sum `*_mg` or `*_stock_uL` over the rows. This is what the chemistry actually
   used: ~13.6 mg substrate and 0.05–0.13 mg photocatalyst *per experiment*.
2. **Prepared** — the stocks were weighed out once for the whole campaign
   (`real_mass_g` in `roboflex_reagents.csv`, 5 mL each: 1.04 g SM, 3.71 g TFAA, 0.94 g py NO,
   ~0.01–0.02 g of each photocatalyst). If unused stock is written off, this is the real spend and
   it dominates the consumed amounts by orders of magnitude.

## Column reference (`roboflex_runs_submitted.csv`)

- `run_id`, `phase`, `bo_campaign_id`, `platform_campaign`, `sample_or_note`
- `status`, `success`, `submitted_to_bo` — `submitted_to_bo=yes` means the result was fed back to the optimizer
- `requested_at` / `started_at` / `finished_at` (UTC), `run_min` (reactor + NMR), `occupied_min` (including queue and robot prep)
- parameters as executed: `catalyst`, `catalyst_equiv`, `oxidant`, `oxidant_equiv`, `TFAA_equiv`,
  `light_intensity_pct`, `residence_time_min`, `slug_volume_uL`, `SM_conc_mM`, `collect_crude`
- amounts: `n_SM_umol`, `SM_mg`, `SM_stock_uL`, and `*_umol` / `*_mg` / `*_stock_uL` for catalyst, TFAA, oxidant
- outcome: `yield_pct`, `green_score`, `nmr_pass`, `nmr_peak_width_ppm`
- `notes` — why a run is invalid, retried, or excluded

## Caveats

- `R0043` was stopped while queued; whether reagents were dispensed is not recorded. Its amounts are
  the planned ones — treat as an upper bound.
- `R0080` was submitted and the platform then became unreachable (HTTP 530); no result came back.
  The reaction most likely ran, so its material is probably spent.
- `R0042`/`R0043` parameters come from the seed plan and their timings from the supervisor log; all
  other rows come from the platform's own run records.
- `green_score` is the agent-defined resource-efficiency metric (0–100, higher = leaner), not a cost.
- Failed runs consumed material exactly like successful ones — 7 of the 37 submissions in the
  reported campaign returned no usable yield.

## Context for the cost comparison

For the reported campaign (`R0042`–`R0080`): 37 submissions, 36 executed, **30 valid measurements**,
best yield **58.8 %** (`R0067`), platform occupied **34.3 h** over a 5.2-day window, **69** operator
turns. Agent-side spend was **\$109.55** in LLM usage (1108 calls, 114.5 M input / 328 k output
tokens), of which 2 h 16 min was actual agent processing time.
