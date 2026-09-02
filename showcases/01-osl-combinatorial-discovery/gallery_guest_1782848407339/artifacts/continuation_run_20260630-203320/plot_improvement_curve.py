#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def nondominated_mask(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(n):
            if i == j or not keep[j]:
                continue
            if np.all(points[j] >= points[i]) and np.any(points[j] > points[i]):
                keep[i] = False
                break
    return keep


def hypervolume_inclusion_exclusion(points: np.ndarray, ref: np.ndarray) -> float:
    points = np.asarray(points, dtype=float)
    if len(points) == 0:
        return 0.0
    nd = points[nondominated_mask(points)]
    hv = 0.0
    m = len(nd)
    for k in range(1, m + 1):
        sign = 1 if k % 2 == 1 else -1
        for idxs in combinations(range(m), k):
            upper = nd[list(idxs)].min(axis=0)
            hv += sign * float(np.prod(np.maximum(0.0, upper - ref)))
    return hv


def build_outputs(artifact_dir: Path) -> dict[str, Path]:
    export_csv = artifact_dir / 'campaign_export.csv'
    report_json = artifact_dir / 'final_report.json'

    if not export_csv.exists():
        raise FileNotFoundError(f'Missing input file: {export_csv}')
    if not report_json.exists():
        raise FileNotFoundError(f'Missing input file: {report_json}')

    df = pd.read_csv(export_csv)
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'])
        df = df.sort_values('created_at').reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    with open(report_json, 'r', encoding='utf-8') as f:
        report = json.load(f)

    osc = df['obj_max_oscillator_strength_s1_s3'].astype(float).to_numpy()
    cerr = df['obj_color_error_eV'].astype(float).to_numpy()
    camb = df['obj_conformational_ambiguity'].astype(float).to_numpy()

    # Convert all objectives into maximization space for Pareto / hypervolume.
    pts = np.column_stack([osc, -cerr, -camb])

    # Conservative buffered reference point derived only from saved objective data.
    ref = np.array([
        min(0.0, float(osc.min()) - 0.05),
        -(float(cerr.max()) + 0.05),
        -(float(camb.max()) + 1.0),
    ], dtype=float)

    n = len(df)
    iters = np.arange(1, n + 1)
    phase = np.where(df['suggestion_id'].isna(), 'seeded', 'live') if 'suggestion_id' in df.columns else np.array(['unknown'] * n)
    seeded_count = int(report.get('seeded_completed_results', 0))

    hv_curve = [hypervolume_inclusion_exclusion(pts[:i], ref) for i in range(1, n + 1)]
    best_osc = [float(np.max(osc[:i])) for i in range(1, n + 1)]
    best_cerr = [float(np.min(cerr[:i])) for i in range(1, n + 1)]
    best_camb = [float(np.min(camb[:i])) for i in range(1, n + 1)]
    pareto_counts = [int(nondominated_mask(pts[:i]).sum()) for i in range(1, n + 1)]

    final_mask = nondominated_mask(pts)
    pareto = df.loc[final_mask].copy().reset_index(drop=True)
    pareto['evaluation'] = np.where(final_mask)[0] + 1
    pareto['phase'] = np.where(pareto['suggestion_id'].isna(), 'seeded', 'live') if 'suggestion_id' in pareto.columns else 'unknown'

    curve_df = pd.DataFrame({
        'evaluation': iters,
        'phase': phase,
        'cap_id': df['param_cap_id'],
        'bridge_id': df['param_bridge_id'],
        'core_id': df['param_core_id'],
        'max_oscillator_strength_s1_s3': osc,
        'color_error_eV': cerr,
        'conformational_ambiguity': camb,
        'best_so_far_max_oscillator_strength_s1_s3': best_osc,
        'best_so_far_color_error_eV': best_cerr,
        'best_so_far_conformational_ambiguity': best_camb,
        'hypervolume_so_far': hv_curve,
        'pareto_count_so_far': pareto_counts,
    })

    curve_csv = artifact_dir / 'updated_improvement_curve_reproducible.csv'
    pareto_csv = artifact_dir / 'pareto_front_updated_reproducible.csv'
    meta_json = artifact_dir / 'updated_improvement_curve_reproducible_metadata.json'
    plot_png = artifact_dir / 'updated_improvement_curve_reproducible.png'

    curve_df.to_csv(curve_csv, index=False)
    pareto.to_csv(pareto_csv, index=False)
    with open(meta_json, 'w', encoding='utf-8') as f:
        json.dump(
            {
                'artifact_dir': str(artifact_dir),
                'input_files': {
                    'campaign_export_csv': str(export_csv),
                    'final_report_json': str(report_json),
                },
                'reference_point_max_space': ref.tolist(),
                'seeded_completed_results': seeded_count,
                'n_results': int(n),
                'final_hypervolume': float(hv_curve[-1]) if hv_curve else 0.0,
                'final_pareto_count': int(final_mask.sum()),
            },
            f,
            indent=2,
        )

    fig, axs = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axs = axs.ravel()

    axs[0].plot(iters, hv_curve, marker='o', color='tab:blue')
    if seeded_count > 0 and seeded_count < n:
        axs[0].axvline(seeded_count + 0.5, color='gray', linestyle='--', alpha=0.8)
    axs[0].set_title('Cumulative Pareto hypervolume')
    axs[0].set_xlabel('Evaluation index')
    axs[0].set_ylabel('Hypervolume')
    axs[0].grid(True, alpha=0.3)

    for ax, obs, best, title, ylabel in [
        (axs[1], osc, best_osc, 'max_oscillator_strength_s1_s3', 'Higher is better'),
        (axs[2], cerr, best_cerr, 'color_error_eV', 'Lower is better'),
        (axs[3], camb, best_camb, 'conformational_ambiguity', 'Lower is better'),
    ]:
        if np.any(phase == 'seeded'):
            ax.scatter(iters[phase == 'seeded'], obs[phase == 'seeded'], color='tab:orange', s=40, alpha=0.85, label='seeded')
        if np.any(phase == 'live'):
            ax.scatter(iters[phase == 'live'], obs[phase == 'live'], color='tab:green', s=40, alpha=0.85, label='live')
        if not np.any((phase == 'seeded') | (phase == 'live')):
            ax.scatter(iters, obs, color='tab:purple', s=40, alpha=0.85, label='observed')
        ax.plot(iters, best, color='black', marker='o', linewidth=1.5, label='best so far')
        if seeded_count > 0 and seeded_count < n:
            ax.axvline(seeded_count + 0.5, color='gray', linestyle='--', alpha=0.8)
        ax.set_title(title)
        ax.set_xlabel('Evaluation index')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False, fontsize=8)

    fig.suptitle('Updated BO improvement curve (reproducible from saved files only)', fontsize=13)
    fig.savefig(plot_png, dpi=180, bbox_inches='tight')
    plt.close(fig)

    return {
        'plot_png': plot_png,
        'curve_csv': curve_csv,
        'pareto_csv': pareto_csv,
        'metadata_json': meta_json,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Rebuild the BO improvement curve from saved campaign files only.')
    parser.add_argument(
        '--artifact-dir',
        type=Path,
        default=Path('artifacts/continuation_run_20260630-203320'),
        help='Artifact directory containing campaign_export.csv and final_report.json',
    )
    args = parser.parse_args()
    outputs = build_outputs(args.artifact_dir)
    for key, value in outputs.items():
        print(f'{key}: {value}')


if __name__ == '__main__':
    main()
