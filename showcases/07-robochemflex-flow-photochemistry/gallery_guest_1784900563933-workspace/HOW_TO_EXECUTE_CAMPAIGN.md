# BO-MCP + RoboFlex/Robridge campaign plan: RoboChemFlex yield optimization

This package prepares a **BayBE-backed BO-MCP campaign** for the current RoboFlex/Robridge setup on Perry. It does **not** request a setup change and does **not** change wavelength, reactor, or vial layout. Real RoboFlex execution is opt-in only.

## Deliverables

- Entrypoint: `run_robochemflex_yield_bo.py`
- Package: `robochemflex_yield_bo/`
- Manifest: `campaign_manifest.json`

## Current platform assumptions checked during authoring

- RoboFlex/Robridge reports Perry in `phase=ready`, `mode=hardware`, `vial_count=19`, no current campaign.
- The completed setup already contains the CSV chemicals/stocks, including `SM`, the five catalysts, `TFAA`, `PyNO`, `4PhPyNO`, and MeCN.
- The campaign uses `Flow Photochemical Reaction` with `NMR` by default. The current Perry `Flow Photochemical Reaction` capability advertises `light_intensity` allowed values `[0, 25, 50, 75, 100]` on the UFlow light array; the user requested no reactor/wavelength setup change, so the script treats light as a discrete BO parameter over those values rather than a continuous 0--100 parameter.

## Search space from local CSV files

Fixed constants from `constants.csv` are sent with each run where applicable:

- `slug_size = 650 uL`
- `collect_crude = FALSE`
- `yield_calculation_chemical = SM`
- `target_peak = -58 ppm`
- `target_peak_deviation = 3 ppm`
- `centerFrequency = -60`
- `AcquisitionTime = 1.64` is sent from `constants.csv` now that the NMR `protocol` is explicitly set to `1D FLUORINE HDEC`.
- `protocol = 1D FLUORINE HDEC` is sent to the RoboFlex NMR analytical parameter `protocol` from constants.csv key `Protocol`.
- `Number = 32`
- `target_peak_calibration_coeff_1 = 6973`
- `target_peak_calibration_coeff_0 = -5.4`

BO-varying variables:

| BO parameter | Type | Range/categories | RoboFlex units |
|---|---:|---|---|
| `catalyst_type` | categorical | `Ru bpy Cl`, `Ru bpy PF6`, `Ir ppy`, `Ir CF3 ppy`, `4CzIPN` | chemical name mapped to active setup stock aliases |
| `oxidant_type` | categorical | `py NO`, `4-Ph py NO` | chemical name mapped to active setup stock aliases |
| `catalyst_equiv` | continuous | 0.001--0.004 equiv | `eq`, role `Catalyst` |
| `TFAA_equiv` | continuous | 0.9--3.5 equiv | `eq`, role `Anhydride` |
| `oxidant_equiv` | continuous | 0.9--3.0 equiv | `eq`, role `Oxidant` |
| `light_intensity` | discrete | 0, 25, 50, 75, 100 | `%` |
| `residence_time_min` | continuous | 2--90 min | converted to seconds for RoboFlex |

`SM` is fixed at 100 mM as the limiting reagent because `chemical_space_reagent_bounds.csv` fixes SM at 100 mM / 65 uL in a 650 uL slug.

## Objectives

1. **Primary objective: `yield_percent`**, maximize. This is extracted from RoboFlex analysed results and clamped to the physically meaningful 0--100% range before submission to BO-MCP.
2. **Secondary objective: `green_score`**, maximize. This is a calculated 0--100 condition-efficiency score:

```text
green_score = 100 * (1 - mean(normalized catalyst loading,
                              normalized TFAA equiv,
                              normalized oxidant equiv,
                              normalized light_intensity * normalized residence_time))
```

Justification: this metric rewards candidates that use less catalyst, less anhydride, less oxidant, and lower photonic residence-time burden while preserving yield as the dominant objective. It is not a formal process mass-intensity or life-cycle metric because product mass and actual energy draw are not returned by the platform, but it is transparent, monotonic in condition resource use, and computable before/after every experiment from submitted or executed conditions.

The BO-MCP intake uses BayBE with desirability scalarization, weights `yield_percent = 0.8` and `green_score = 0.2`, and normalized objective bounds `[0, 100]` for both. This keeps yield primary while allowing the optimizer to prefer greener conditions when yields are comparable.

## BO strategy

- **Optimizer/backend:** BO-MCP with `backend="baybe"`.
- **Surrogate/acquisition:** BayBE's Bayesian recommender is requested via BO-MCP with Expected Improvement semantics. BO-MCP owns the concrete BayBE model/recommender internals and campaign state.
- **Batch size:** 1. RoboFlex executes one queued flow experiment at a time, and sequential feedback is more sample-efficient for only 20 total experiments.
- **Budget:** 20 successful evaluations total. The recommended allocation is 6 informed seed experiments followed by 14 sequential BO-recommended experiments.
- **Stopping criterion:** stop after 20 successful evaluations or earlier if BO-MCP `next_action` says not to generate more suggestions. The script treats `--max-successes` as a per-invocation budget, not an immutable campaign cap, so a paused campaign can be resumed.
- **Failure supervision:** failed RoboFlex/NMR analyses are not submitted to BO-MCP, are not counted as successful experiments, and stop the invocation with an alert. The script refuses visible queued/running RoboFlex runs before starting/submitting more hardware work and refuses duplicate sample labels unless a hardware retry is explicitly acknowledged with `--allow-hardware-retry --retry-suffix <suffix>`.
- **Quiet supervision:** hardware polling prints only run/platform state changes, low-frequency heartbeats, and final per-experiment summaries or alerts; detailed records go to JSONL artifacts.
- **Constraints:** all bounds come from the CSVs plus the RoboFlex capability constraint that UFlow light intensity is settable only at 0/25/50/75/100%. No setup, reactor, or wavelength changes are requested.
- **Transfer learning/warm start:** no prior campaign id or historical yield dataset was supplied. The package therefore uses chemically informed seed experiments rather than BO-MCP transfer-learning configuration. If a compatible prior BO-MCP campaign is later supplied, add it as a future change after checking BayBE-compatible transfer semantics.

## Informed initial seed design

The six seeds deliberately cover catalyst families, oxidant identity, reagent-loading extremes, light-intensity levels, and residence-time regimes without spending the whole 20-run budget:

| Seed | catalyst | oxidant | cat eq | TFAA eq | oxidant eq | light % | residence min | Role |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | 4CzIPN | py NO | 0.0025 | 2.2 | 1.8 | 50 | 30 | center/baseline with organic photocatalyst |
| 2 | Ru bpy Cl | py NO | 0.0010 | 0.9 | 0.9 | 75 | 10 | low-loading, short-residence lower-resource point |
| 3 | Ir CF3 ppy | 4-Ph py NO | 0.0040 | 3.5 | 3.0 | 100 | 75 | high-driving-force/high-input corner |
| 4 | Ir ppy | py NO | 0.0020 | 1.4 | 2.4 | 25 | 45 | low-light Ir comparison |
| 5 | Ru bpy PF6 | 4-Ph py NO | 0.0035 | 3.0 | 1.2 | 75 | 20 | Ru/PF6 and oxidant-identity contrast |
| 6 | 4CzIPN | 4-Ph py NO | 0.0015 | 1.7 | 2.5 | 50 | 90 | organic photocatalyst at long residence, moderate inputs |

Scientific rationale: current reviews of BO for reaction optimization describe an initialization phase using deliberate experimental design such as LHS/DoE before sequential model updates, particularly for mixed categorical/continuous chemical spaces where full-factorial screening is too expensive. Self-driving-lab guidance similarly recommends diverse, space-filling initial data, while noting that a small seed set leaves more budget for BO. Photoredox flow reviews emphasize that catalyst identity, light intensity/photon flux, concentration/loading, and residence time strongly affect photochemical performance, and that flow improves photochemical efficiency and makes residence-time/light-intensity optimization practical. The seeds are therefore not random: they are a small, chemistry-aware coverage design across catalyst photophysics/redox classes, oxidant identity, stoichiometry, photon dose, and residence time.

Sources consulted:

- RSC Chemical Society Reviews, 2026, "Bayesian optimization for chemical reactions": https://pubs.rsc.org/en/content/articlehtml/2026/cs/d5cs00962f
- RSC Digital Discovery, 2026, "A user's guide to your first self-driving liquid handling lab": https://pubs.rsc.org/en/content/articlehtml/2026/dd/d5dd00525f
- ACS Chemical Reviews, "Self-Driving Laboratories for Chemistry and Materials Science": https://pubs.acs.org/doi/10.1021/acs.chemrev.4c00055
- ACS Chemical Reviews, "Technological Innovations in Photochemistry for Organic Synthesis: Flow Chemistry, High-Throughput Experimentation, Scale-up, and Photoelectrochemistry": https://pubs.acs.org/doi/10.1021/acs.chemrev.1c00332
- ChemPhotoChem, "Effects of Light Intensity and Reaction Temperature on Photoreactions in Commercial Photoreactors": https://chemistry-europe.onlinelibrary.wiley.com/doi/full/10.1002/cptc.202100059
- ChemPhotoChem, "Heuristics, Protocol, and Considerations for Flow Chemistry in Photoredox Catalysis": https://chemistry-europe.onlinelibrary.wiley.com/doi/10.1002/cptc.201700128
- PMC review, "The Development of Visible-Light Photoredox Catalysis in Flow": https://pmc.ncbi.nlm.nih.gov/articles/PMC4255365/
- BayBE documentation, "Recommenders" and "Campaigns": https://emdgroup.github.io/baybe/stable/index.html

## How to validate without real experiments

Use local simulation only. This creates a BO-MCP campaign and submits one synthetic result, but it does not call RoboFlex POST endpoints and does not touch hardware.

```bash
uv run python run_robochemflex_yield_bo.py \
  --mode local-simulation \
  --skip-informed-seeds \
  --max-successes 1 \
  --campaign-name robochemflex_yield_baybe_smoke \
  --artifact-dir artifacts/smoke_robochemflex_yield_bo \
  --terminate-bo-on-exit
```

## Patch note after failed real run R0042

The first real attempt failed during NMR analysis, not during BO result submission. The package now sends the explicit NMR analytical parameter `protocol='1D FLUORINE HDEC'` from constants.csv key `Protocol`, avoiding the default proton/`1D EXTENDED+` protocol. With that protocol explicit, `AcquisitionTime='1.64'` is again sent directly from `constants.csv`. Run `R0042` and the stopped queued duplicate `R0043` must not be submitted to BO-MCP as measurements because neither produced a valid yield.

Before resuming hardware, confirm there are no queued/running runs left from the stopped RoboFlex campaign:

```bash
uv run python - <<'PY'
from domains.roboflex.tools import fetch_roboflex_text
print(fetch_roboflex_text('/v1/runs'))
PY
```

If `R0043` is still listed as `queued` or `running`, do **not** resume; wait for it to be marked failed/cleared by the stopped campaign or ask the operator. Once no unfinished runs are visible, the corrected retry of seed 1 is intentional and should use a new sample suffix.

Recommended resume command for the existing BO campaign after `R0043` is no longer queued/running:

```bash
uv run python run_robochemflex_yield_bo.py \
  --mode robridge-real \
  --allow-real-roboflex \
  --allow-hardware-retry \
  --retry-suffix r2 \
  --campaign-id 1d62df6d-764a-4cf3-b857-b21482da74a0 \
  --campaign-name robochemflex_yield_baybe_real_20260724T141938Z \
  --artifact-dir artifacts/real_robochemflex_yield_bo_resume_r2 \
  --max-successes 20
```

## How to run the real campaign later (operator approval required)

Do not run this unless the user explicitly authorizes real experiments.

1. Confirm the current vial setup is still the intended Perry setup:

```bash
uv run python - <<'PY'
from domains.roboflex.tools import fetch_roboflex_text
print(fetch_roboflex_text('/v1/status'))
PY
```

2. Provide a trusted operator-approved `ROBRIDGE_POST_ADAPTER` executable. It must accept `POST` and path arguments, read the JSON body from stdin, send the exact documented Robridge request shape with `X-API-Key` from `ROBOFLEX_API_KEY` and an accepted User-Agent, and write the JSON response to stdout. This adapter boundary is used because the canonical RoboFlex helper available in this environment is GET-only.

3. Start/resume the campaign:

```bash
uv run python run_robochemflex_yield_bo.py \
  --mode robridge-real \
  --allow-real-roboflex \
  --max-successes 20
```

4. If interrupted, resume without replaying local state:

```bash
uv run python run_robochemflex_yield_bo.py \
  --mode robridge-real \
  --allow-real-roboflex \
  --campaign-id <existing-bo-campaign-id> \
  --max-successes 20
```

The BO-MCP server owns campaign state. Artifact files are provenance only and are not read back for loop decisions.
