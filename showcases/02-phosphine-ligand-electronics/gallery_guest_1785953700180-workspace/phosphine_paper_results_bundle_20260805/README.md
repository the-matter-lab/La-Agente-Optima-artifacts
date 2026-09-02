# Phosphine ligand electronic-tuning BO paper-results bundle

This folder collects the campaign outputs, logs, plots, and plotting scripts for the finite-candidate phosphine ligand electronic-tuning BO campaign.

## Campaign identity

- BO-MCP campaign ID: `f4e94d3d-0e06-43aa-baab-8bb15da9b843`
- Cumulative artifact directory copied here: `campaign_artifacts/phosphine_electronics_20260805_182629/`
- Final campaign size: 48 successful evaluations = 8 warm-start + 40 BO-guided evaluations
- Failed evaluations: 0
- Final observed Pareto-front size: 17

## Key files for analysis/writeup

Inside `campaign_artifacts/phosphine_electronics_20260805_182629/`:

- `report.md` — human-readable campaign report with representative trade-off ligands and trends.
- `report.csv` — flattened descriptor/objective table with Pareto/trade-off flags.
- `evaluation_records.jsonl` — full per-evaluation records in chronological order.
- `bo_mcp_export.csv` — exported BO-MCP campaign/result table.
- `warm_start_rationale.csv` — initial-design ligand choices and rationale.
- `campaign_id.txt` — campaign UUID.
- `run.log` — detailed campaign logger output.
- `plots/` — regenerated summary plots after the 48-evaluation campaign.
- `bo_improvement_curve.png` and `bo_improvement_curve.csv` — cumulative improvement curve and underlying data.

## Plot scripts

- `plot_scripts/plot_bo_improvement_curve.py`
- `plot_scripts/plot_phosphine_campaign_summary.py`

These scripts read campaign artifacts (`evaluation_records.jsonl`, `report.csv`) and do not hard-code result values.

To regenerate plots from the repository/workspace root, copy or run the scripts with:

```bash
PYTHONUNBUFFERED=1 uv run python plot_bo_improvement_curve.py \
  --artifact-dir artifacts/phosphine_electronics_20260805_182629

PYTHONUNBUFFERED=1 uv run python plot_phosphine_campaign_summary.py \
  --artifact-dir artifacts/phosphine_electronics_20260805_182629
```

If running from this bundle only, either preserve the relative artifact path expected by the scripts or pass `--artifact-dir campaign_artifacts/phosphine_electronics_20260805_182629`.

## Monitor logs

`monitor_logs/` contains stdout monitor captures for the original and continuation runs. Note: the original run's monitor log captured only early `[EVENT]` lines because threaded PySCF stdout redirection swallowed later tagged stdout; the full progress is in `campaign_artifacts/.../run.log` and `evaluation_records.jsonl`. The continuation run used the patched evaluator/safer worker settings and produced monitor-visible tagged progress.

## Campaign code

`campaign_code/` contains the runnable campaign entrypoint and package used to produce the final results, including the pre-enumerated 364-row candidate table.

## Suggested paper-section source hierarchy

1. Use `report.csv` / `evaluation_records.jsonl` for quantitative tables.
2. Use `report.md` for concise narrative, representative ligands, failure summary, and trend interpretation.
3. Use `plots/` and `bo_improvement_curve.png` for figures.
4. Use `warm_start_rationale.csv` to describe initial design.
5. Use `metadata/HOW_TO_EXECUTE_CAMPAIGN.md` for protocol and reproducibility details.
