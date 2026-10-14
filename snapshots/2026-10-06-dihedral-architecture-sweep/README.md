# Butanol dihedral benchmark — four-architecture sweep (GPT-5.4, 3 repeats)

Final sweep of the butanol three-dihedral benchmark: the proposed architecture (`Specialist-script`) and the
`Main-script`, `Tool-loop` and `Local-BO` ablations, 3 repeats each, run on 2026-10-06 (09:19–16:37 EDT) on the goethe
workstation. All 12 repeats completed cleanly; total model cost $24.96.

## Protocol

- Task: minimize the PBE-D4/def2-SVP single-point energy of butanol over its three dihedral angles (including the
  O–H hydrogen), 60 attempted objective evaluations per repeat. The user prompt is the unchanged example
  `examples/bo-mcp/dihedral_angle_optimization.md` (`prompt.txt` in each cell).
- Code: akg4pyscf `0949c2d1` (branch `agent/dihedral-benchmark-on-main`, marcelmbn/akg4pyscf#65), the same commit for
  all 12 repeats (`raw/launch_records/pinned_commit.txt`).
- Model: gpt-5.4 through the LiteLLM gateway (`litellm-openai-responses`); BO backend BayBE; agent time limit 5400 s;
  PySCF runner image `ecb0cf0adc4a`, profile `cpu-smoke` (16384 MB).
- Validity is checked from the PySCF runner's own batch records, not from the agent's report: at least 60 calls with an
  explicit geometry and PBE-D4/def2-SVP that completed only a single-point calculation. All 12 repeats are verified
  (`raw/launch_records/audit_runs.json`). A separate re-check of the same records found that all 783 PySCF calls
  finished with a converged SCF energy, and that each of the 720 reported points matches, one to one, the energy and
  the three dihedral angles of the geometry that was actually computed.

## Architectures

| Folder | Architecture | Description |
|---|---|---|
| `standard_gpt54` | **Specialist-script** (proposed; called "Standard" in the report and code) | main agent delegates to a BO specialist that writes and runs the campaign script against BO-MCP |
| `main_script_gpt54` | Main-script | the main agent writes and runs the BO-MCP campaign script itself |
| `direct_tool_gpt54` | Tool-loop | the main agent drives BO-MCP through tool calls, no campaign script |
| `no_bo_gpt54` | Local-BO | the main agent runs BayBE locally in its own script, no BO-MCP |

## Results

| Architecture | Best energy (Ha) | Normalized AUC @10 / 30 / 60 evals | Cost per repeat | Time per repeat |
|---|---:|---:|---:|---:|
| Specialist-script | −233.186543 | 0.79 / 0.89 / 0.92 | $2.65 | 54 min |
| Main-script | −233.187339 | 0.69 / 0.83 / 0.91 | $1.68 | 25 min |
| Tool-loop | −233.186294 | 0.54 / 0.78 / 0.88 | $3.01 | 23 min |
| Local-BO | −233.186816 | 0.69 / 0.84 / 0.91 | $0.98 | 42 min |

Final quality is a tie: best energies agree within 0.66 kcal/mol, and raw energies do not rank the architectures
because each run prepares its own reference geometry. After aligning per-run offsets, all three Specialist-script
runs, all three Main-script runs and Tool-loop r03 reach the same minimum within 0.03 kcal/mol. Local-BO r01 and r03
built the molecule by hand with their own angle convention, so their energies are not directly comparable. In
Local-BO r02 the agent's first campaign reused its smoke test's batch name and lost 3 evaluations, so it ran a fresh
60-evaluation campaign and reported only that one; its `metrics.json` therefore counts 117 PySCF calls, its time
includes the discarded campaign, and the discarded campaign's best was 0.24 kcal/mol lower than the reported one. The
architectures differ in convergence speed, cost and time; Specialist-script converges fastest per evaluation, and
Main-script is the best balance. Full analysis: `report/DIHEDRAL_ARCHITECTURE_COMPARISON_2026-10-06.pdf`.

## Contents

- `raw/<arm>/dihedral/r0N/eval/`: per repeat, `run_manifest.json`, `summary.json`, `summary.md` and
  `cases/dihedral/{metrics.json, prompt.txt}`; Local-BO cells also have `local_results.json`.
  `raw/<arm>/dihedral/repeat_summary.{json,md}` summarize each arm. Layout mirrors `snapshots/2026-08-08-current/raw/`.
- `raw/launch_records/`: the per-repeat audit, the pinned commit, and per-arm launch commit and installed-package list.
- `report/`: the 9-page comparison report (PDF), its figures, the extracted data (`data/`) and the scripts that built
  it (`extract_data.py`, `generate_report.py`, `build_pdf.py`; they contain the absolute paths of the research
  workstation).

Conversations, agent outputs, logs and PySCF runner records are not included. They remain on the research workstation.

## Sanitization

Some Specialist-script cells recorded the run environment's API keys and tokens, which the BO specialist printed while
inspecting its setup. Every value of a credential-named environment variable found in the run tree was replaced with
`[REDACTED]`, then `scripts/sanitize_snapshot.py` was applied (counts in `SANITIZATION_REPORT.json`), and the snapshot
was re-scanned for those values and for key-shaped strings: none remain. The originals were not modified.
