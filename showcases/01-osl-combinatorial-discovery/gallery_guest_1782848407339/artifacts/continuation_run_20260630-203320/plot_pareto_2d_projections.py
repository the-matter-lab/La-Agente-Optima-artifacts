#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def build_plot(artifact_dir: Path) -> dict[str, Path]:
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

    df['evaluation'] = np.arange(1, len(df) + 1)
    df['phase'] = np.where(df['suggestion_id'].isna(), 'seeded', 'live') if 'suggestion_id' in df.columns else 'unknown'

    osc = df['obj_max_oscillator_strength_s1_s3'].astype(float).to_numpy()
    cerr = df['obj_color_error_eV'].astype(float).to_numpy()
    camb = df['obj_conformational_ambiguity'].astype(float).to_numpy()
    pts = np.column_stack([osc, -cerr, -camb])
    mask = nondominated_mask(pts)
    pareto = df.loc[mask].copy().reset_index(drop=True)

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)

    colors = {'seeded': 'tab:orange', 'live': 'tab:green', 'unknown': 'tab:purple'}

    def scatter_panel(ax, xcol, ycol, xlabel, ylabel, x_better, y_better):
        for phase in ['seeded', 'live', 'unknown']:
            sub = df[df['phase'] == phase]
            if len(sub) == 0:
                continue
            ax.scatter(sub[xcol], sub[ycol], s=40, alpha=0.45, color=colors[phase], label=f'{phase} (all)')
        ax.scatter(pareto[xcol], pareto[ycol], s=85, facecolors='none', edgecolors='black', linewidths=1.5, label='Pareto-optimal')
        for _, row in pareto.iterrows():
            ax.annotate(str(int(row['evaluation'])), (row[xcol], row[ycol]), textcoords='offset points', xytext=(4, 4), fontsize=8)
        ax.set_xlabel(f'{xlabel} ({x_better})')
        ax.set_ylabel(f'{ylabel} ({y_better})')
        ax.grid(True, alpha=0.3)

    scatter_panel(
        axs[0],
        'obj_max_oscillator_strength_s1_s3',
        'obj_color_error_eV',
        'max_oscillator_strength_s1_s3',
        'color_error_eV',
        'higher is better',
        'lower is better',
    )
    scatter_panel(
        axs[1],
        'obj_max_oscillator_strength_s1_s3',
        'obj_conformational_ambiguity',
        'max_oscillator_strength_s1_s3',
        'conformational_ambiguity',
        'higher is better',
        'lower is better',
    )
    scatter_panel(
        axs[2],
        'obj_color_error_eV',
        'obj_conformational_ambiguity',
        'color_error_eV',
        'conformational_ambiguity',
        'lower is better',
        'lower is better',
    )

    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=4, frameon=False)
    fig.suptitle('2D Pareto projections from saved campaign files only', fontsize=13)

    plot_png = artifact_dir / 'pareto_2d_projections_reproducible.png'
    pareto_csv = artifact_dir / 'pareto_front_updated_reproducible.csv'
    panel_csv = artifact_dir / 'pareto_2d_projection_points.csv'
    meta_json = artifact_dir / 'pareto_2d_projections_reproducible_metadata.json'

    fig.savefig(plot_png, dpi=180, bbox_inches='tight')
    plt.close(fig)

    if not pareto_csv.exists():
        pareto.to_csv(pareto_csv, index=False)

    df.to_csv(panel_csv, index=False)

    with open(meta_json, 'w', encoding='utf-8') as f:
        json.dump(
            {
                'artifact_dir': str(artifact_dir),
                'input_files': {
                    'campaign_export_csv': str(export_csv),
                    'final_report_json': str(report_json),
                },
                'seeded_completed_results': int(report.get('seeded_completed_results', 0)),
                'n_results': int(len(df)),
                'final_pareto_count': int(mask.sum()),
                'pareto_evaluations': [int(x) for x in pareto['evaluation'].tolist()],
            },
            f,
            indent=2,
        )

    return {
        'plot_png': plot_png,
        'panel_csv': panel_csv,
        'pareto_csv': pareto_csv,
        'metadata_json': meta_json,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Build 2D Pareto projection plots from saved campaign files only.')
    parser.add_argument(
        '--artifact-dir',
        type=Path,
        default=Path('artifacts/continuation_run_20260630-203320'),
        help='Artifact directory containing campaign_export.csv and final_report.json',
    )
    args = parser.parse_args()
    outputs = build_plot(args.artifact_dir)
    for key, value in outputs.items():
        print(f'{key}: {value}')


if __name__ == '__main__':
    main()
